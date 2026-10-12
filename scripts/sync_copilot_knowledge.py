"""Push knowledge files to a Copilot Studio agent through the Dataverse Web API.

Copilot Studio stores each uploaded knowledge file as a row of the `botcomponents` table
(componenttype 14, "Bot File Attachment") linked to the agent, with the file itself in the
`filedata` column. This script reproduces what the "Upload file" button does:

  1. create a new component row and upload the file into it,
  2. delete the previous version of the same file (after the upload, so the agent is never
     left without the document),
  3. optionally publish the agent so the change reaches published channels.
     The Copilot Studio test pane uses the latest draft and sees the change without publishing.

Authentication: an Entra ID app registration (client credentials) that is registered as an
application user in the Power Platform environment. See docs/knowledge-sync.md.

Environment variables
  DATAVERSE_URL         https://<org>.crm<N>.dynamics.com
  AZURE_TENANT_ID       Entra tenant id
  AZURE_CLIENT_ID       app registration (client) id
  AZURE_CLIENT_SECRET   app registration secret
  COPILOT_AGENT_ID      agent id (the GUID after /bots/ in the Copilot Studio URL)

Usage
  python scripts/sync_copilot_knowledge.py --list
  python scripts/sync_copilot_knowledge.py build/knowledge/01-incident-runbook.docx --publish
  python scripts/sync_copilot_knowledge.py --delete 04-old-policy.docx
  python scripts/sync_copilot_knowledge.py build/knowledge/*.docx --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

FILE_ATTACHMENT = 14  # botcomponent.componenttype "Bot File Attachment"
API = "/api/data/v9.2/"


class Dataverse:
    def __init__(self, url: str, token: str):
        self.base = url.rstrip("/") + API
        self.token = token

    def request(self, method: str, path: str, body=None, headers=None, raw: bytes | None = None):
        hdrs = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "OData-Version": "4.0",
            "OData-MaxVersion": "4.0",
        }
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            hdrs["Content-Type"] = "application/json; charset=utf-8"
        hdrs.update(headers or {})
        # OData queries contain spaces and quotes: encode them, keep OData syntax characters.
        url = self.base + urllib.parse.quote(path, safe="/()$=&,?'@.:-_")
        req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                payload = resp.read()
                return resp.headers, (json.loads(payload) if payload else None)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:800]
            raise SystemExit(f"Dataverse {method} {path} failed: HTTP {e.code}\n{detail}") from None

    def get(self, path: str):
        return self.request("GET", path)[1]


def get_token(tenant: str, client_id: str, secret: str, resource: str) -> str:
    form = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
        "scope": resource.rstrip("/") + "/.default",
    }).encode()
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=form), timeout=30) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Token request failed: HTTP {e.code}\n{e.read().decode(errors='replace')[:500]}")


def list_files(dv: Dataverse, agent_id: str) -> dict[str, list[str]]:
    """File name -> ids of the components holding it (several if duplicates exist)."""
    query = (
        f"botcomponents?$select=botcomponentid,name&$filter=_parentbotid_value eq {agent_id}"
        f" and componenttype eq {FILE_ATTACHMENT}"
    )
    files: dict[str, list[str]] = {}
    for row in dv.get(query)["value"]:
        files.setdefault(row["name"], []).append(row["botcomponentid"])
    return files


def upload(dv: Dataverse, agent_id: str, agent_schema: str, path: Path) -> str:
    # Copilot Studio names file components "<agent schema>.file.<file name>_<3 random chars>".
    suffix = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(3))
    headers, _ = dv.request(
        "POST",
        "botcomponents",
        body={
            "name": path.name,
            "componenttype": FILE_ATTACHMENT,
            "schemaname": f"{agent_schema}.file.{path.name}_{suffix}",
            "description": f"This knowledge source searches information contained in {path.name}",
            "parentbotid@odata.bind": f"/bots({agent_id})",
        },
    )
    entity_url = headers.get("OData-EntityId", "")
    component_id = entity_url[entity_url.rfind("(") + 1 : -1]
    dv.request(
        "PATCH",
        f"botcomponents({component_id})/filedata",
        raw=path.read_bytes(),
        headers={"Content-Type": "application/octet-stream", "x-ms-file-name": path.name},
    )
    return component_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync knowledge files to a Copilot Studio agent")
    parser.add_argument("files", nargs="*", type=Path, help="files to add or replace")
    parser.add_argument("--delete", nargs="*", default=[], metavar="NAME", help="file names to remove")
    parser.add_argument("--publish", action="store_true", help="publish the agent after the changes")
    parser.add_argument("--list", action="store_true", help="only list the agent's knowledge files")
    parser.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    args = parser.parse_args()

    env = {k: os.environ.get(k, "") for k in (
        "DATAVERSE_URL", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "COPILOT_AGENT_ID")}
    missing = [k for k, v in env.items() if not v]
    if missing:
        raise SystemExit(f"Missing environment variables: {', '.join(missing)}")
    for path in args.files:
        if not path.is_file():
            raise SystemExit(f"File not found: {path}")

    token = get_token(env["AZURE_TENANT_ID"], env["AZURE_CLIENT_ID"],
                      env["AZURE_CLIENT_SECRET"], env["DATAVERSE_URL"])
    dv = Dataverse(env["DATAVERSE_URL"], token)
    agent_id = env["COPILOT_AGENT_ID"]
    agent = dv.get(f"bots({agent_id})?$select=name,schemaname")
    current = list_files(dv, agent_id)
    print(f"Agent: {agent['name']} ({agent['schemaname']}), {len(current)} knowledge file(s)")

    if args.list:
        for name, ids in sorted(current.items()):
            print(f"  {name}" + (f"  ({len(ids)} copies)" if len(ids) > 1 else ""))
        return 0

    changed = False
    for path in args.files:
        old_ids = current.get(path.name, [])
        action = "replace" if old_ids else "add"
        print(f"  {action:7} {path.name}")
        if args.dry_run:
            continue
        new_id = upload(dv, agent_id, agent["schemaname"], path)
        for old_id in old_ids:
            dv.request("DELETE", f"botcomponents({old_id})")
        print(f"          uploaded as component {new_id}" + (f", removed {len(old_ids)} old" if old_ids else ""))
        changed = True

    for name in args.delete:
        ids = current.get(name, [])
        print(f"  delete  {name}" + ("" if ids else "  (not in the agent, skipped)"))
        if args.dry_run:
            continue
        for old_id in ids:
            dv.request("DELETE", f"botcomponents({old_id})")
            changed = True

    if args.dry_run:
        print("Dry run: nothing changed.")
        return 0
    if not changed:
        print("Nothing to change.")
        return 0

    print("Files uploaded: Copilot Studio indexes them in a few minutes (status 'Ready').")
    if args.publish:
        try:
            _, result = dv.request("POST", f"bots({agent_id})/Microsoft.Dynamics.CRM.PvaPublish", body={})
            print(f"Publish requested: {json.dumps(result)[:200] if result else 'ok'}")
        except SystemExit as e:
            # A Copilot Studio trial cannot publish by default. The files are still in the agent
            # and the test pane uses them, so this is a warning, not a failure.
            print(f"::warning::Files synced but publishing failed (trial licenses cannot publish by default).\n{e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
