"""One-time guarded-mode upgrade to ElyraOps v0.3. Run from repository root."""
from pathlib import Path


PLANNED = {}


def edit(path, operations):
    file = Path(path)
    original = file.read_text()
    modified = original
    for old, new in operations:
        matches = modified.count(old)
        expected = 2 if old == "'<button class=\"primary\" id=\"newCase\">+ Create case</button>'" else 1
        if matches != expected:
            raise SystemExit(f"STOP: {path}: expected {expected} matching patch anchor(s), found {matches}; no file was written")
        modified = modified.replace(old, new, expected)
    PLANNED[path] = modified
    print("Validated", path)


def main():
    assert Path('elyraops/core.py').exists(), 'Run from the ElyraOps repository root'
    edit('elyraops/core.py', [
        ('def list_cases():\n    with connect() as db:\n        return [dict(r) for r in db.execute("SELECT id,title,domain,priority,organization,description,status,created_at,updated_at FROM cases ORDER BY id")]',
         'def list_cases(organization=None):\n    with connect() as db:\n        query = "SELECT id,title,domain,priority,organization,description,status,created_at,updated_at FROM cases"\n        if organization is None:\n            return [dict(r) for r in db.execute(query + " ORDER BY id")]\n        return [dict(r) for r in db.execute(query + " WHERE organization=? ORDER BY id", (organization,))]'),
        ('def get_case(case_id):\n    with connect() as db:\n        r = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()',
         'def get_case(case_id, organization=None):\n    with connect() as db:\n        if organization is None:\n            r = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()\n        else:\n            r = db.execute("SELECT * FROM cases WHERE id=? AND organization=?", (case_id, organization)).fetchone()'),
        ('def investigate(case_id):\n    with transaction() as db:\n        row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()',
         'def investigate(case_id, organization=None):\n    with transaction() as db:\n        if organization is None:\n            row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()\n        else:\n            row = db.execute("SELECT * FROM cases WHERE id=? AND organization=?", (case_id, organization)).fetchone()'),
        ('def decide(case_id, decision, actor):', 'def decide(case_id, decision, actor, organization=None):'),
        ('    with transaction() as db:\n        r = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()\n        if not r:\n            raise KeyError(case_id)\n        if r["status"] != "Pending approval":',
         '    with transaction() as db:\n        if organization is None:\n            r = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()\n        else:\n            r = db.execute("SELECT * FROM cases WHERE id=? AND organization=?", (case_id, organization)).fetchone()\n        if not r:\n            raise KeyError(case_id)\n        if r["status"] != "Pending approval":'),
        ('def dashboard():\n    cases = list_cases()', 'def dashboard(organization=None):\n    cases = list_cases(organization)'),
        ('def create_case(payload):', 'def create_case(payload, organization=None):'),
        ('    organization = str(payload.get("organization", "Demo organization")).strip()',
         '    organization = str(organization if organization is not None else payload.get("organization", "Demo organization")).strip()'),
        ('Authentication and tenant authorization are not\nimplemented and must be added before exposing real business data.',
         'fully implemented. An opt-in HTTP access guard provides demo-only\nrole and organization scoping; do not expose real business data.'),
    ])

    edit('elyraops/agent_client.py', [
        ('from urllib.request import Request, urlopen\n', 'from urllib.request import Request, urlopen\n\nfrom . import security\n'),
        ('def investigate(case_id:str) -> dict:', 'def investigate(case_id:str, organization:str | None = None) -> dict:'),
        ('    if os.environ.get("ELYRA_AGENT_TOKEN"):\n        headers["X-Agent-Token"]=os.environ["ELYRA_AGENT_TOKEN"]\n    request=Request(base+"/v1/investigate",json.dumps({"case_id":case_id}).encode(),headers,method="POST")',
         '    internal=os.environ.get("ELYRA_AGENT_TOKEN", "")\n    if security.enabled() and len(internal) < 32:\n        raise AgentUnavailable("An internal agent token of at least 32 characters is required")\n    if internal:\n        headers["X-Agent-Token"]=internal\n    if security.enabled() and not organization:\n        raise AgentUnavailable("Scoped organization required for guarded agent request")\n    body={"case_id":case_id}\n    if organization is not None:\n        body["organization"]=organization\n    request=Request(base+"/v1/investigate",json.dumps(body).encode(),headers,method="POST")'),
    ])

    edit('agent_service/app.py', [
        ('from elyraops import core\n', 'from elyraops import core, security\n'),
        ('    case_id: str = Field(pattern=r"^EC-[A-Za-z0-9-]+$", max_length=70)\n',
         '    case_id: str = Field(pattern=r"^EC-[A-Za-z0-9-]+$", max_length=70)\n    organization: str | None = Field(default=None, min_length=1, max_length=100)\n'),
        ('    token=os.environ.get("ELYRA_AGENT_TOKEN", "")\n    if token and x_agent_token != token:\n        raise HTTPException(401,"Invalid internal service token")\n    core.initialize()\n    case=core.get_case(payload.case_id)',
         '    try:\n        valid = security.internal_token_valid(x_agent_token)\n    except security.SecurityError as exc:\n        raise HTTPException(exc.status, str(exc)) from exc\n    if not valid:\n        raise HTTPException(401, "Invalid internal service token")\n    scoped=security.enabled()\n    if scoped and not payload.organization:\n        raise HTTPException(400, "Trusted organization required")\n    core.initialize()\n    case=core.get_case(payload.case_id, payload.organization if scoped else None)'),
        ('        fresh=db.execute("SELECT status,workflow_run_id FROM cases WHERE id=?",(payload.case_id,)).fetchone()',
         '        if scoped:\n            fresh=db.execute("SELECT status,workflow_run_id FROM cases WHERE id=? AND organization=?",(payload.case_id,payload.organization)).fetchone()\n        else:\n            fresh=db.execute("SELECT status,workflow_run_id FROM cases WHERE id=?",(payload.case_id,)).fetchone()'),
    ])

    edit('elyraops/server.py', [
        ('from . import agent_client\n', 'from . import agent_client\nfrom . import security\n'),
        ('        if path == "/api/dashboard":\n            return self.write_json(core.dashboard())',
         '        if path == "/api/auth/config":\n            try:\n                return self.write_json({"enabled": security.enabled()})\n            except security.SecurityError as exc:\n                return self.write_json({"error": str(exc)}, exc.status)\n        if path.startswith("/api/"):\n            try:\n                principal = security.authenticate(self.headers.get("Authorization"))\n                security.authorize(principal, "read")\n            except security.SecurityError as exc:\n                return self.write_json({"error": str(exc)}, exc.status)\n            organization = principal.organization if principal else None\n        else:\n            principal = None\n            organization = None\n        if path == "/api/auth/me":\n            return self.write_json({"enabled": bool(principal), "name": principal.name if principal else "Demo operator", "role": principal.role if principal else "demo", "organization": organization})\n        if path == "/api/dashboard":\n            return self.write_json(core.dashboard(organization))'),
        ('            return self.write_json({"items": core.list_cases()})',
         '            return self.write_json({"items": core.list_cases(organization)})'),
        ('            case = core.get_case(match.group(1))',
         '            case = core.get_case(match.group(1), organization)'),
        ('        try:\n            payload = self.read_json()',
         '        try:\n            principal = security.authenticate(self.headers.get("Authorization"))\n            payload = self.read_json()'),
        ('            if path == "/api/cases":\n                return self.write_json(core.create_case(payload), 201)',
         '            if path == "/api/cases":\n                security.authorize(principal, "create")\n                return self.write_json(core.create_case(payload, principal.organization if principal else None), 201)'),
        ('                if operation == "investigate":\n                    return self.write_json(agent_client.investigate(case_id) if os.environ.get("ELYRA_AGENT_URL") else core.investigate(case_id))\n                return self.write_json(core.decide(case_id, payload.get("decision"), payload.get("actor")))',
         '                organization = principal.organization if principal else None\n                if operation == "investigate":\n                    security.authorize(principal, "investigate")\n                    if not core.get_case(case_id, organization):\n                        return self.write_json({"error": "Case not found"}, 404)\n                    return self.write_json(agent_client.investigate(case_id, organization) if os.environ.get("ELYRA_AGENT_URL") else core.investigate(case_id, organization))\n                security.authorize(principal, "decide")\n                return self.write_json(core.decide(case_id, payload.get("decision"), principal.name if principal else payload.get("actor"), organization))'),
        ('        except agent_client.AgentUnavailable as exc:',
         '        except security.SecurityError as exc:\n            return self.write_json({"error": str(exc)}, exc.status)\n        except agent_client.AgentUnavailable as exc:'),
        ('    print(f"ElyraOps AI demo at http://{host}:{port} | {mode} | No authentication", flush=True)',
         '    security_mode = "GUARDED LOCAL API" if security.enabled() else "UNGUARDED DEMO"\n    if security.enabled() and host not in {"127.0.0.1", "localhost"}:\n        raise RuntimeError("Guarded demo must bind to localhost; public exposure is unsupported")\n    print(f"ElyraOps AI demo at http://{host}:{port} | {mode} | {security_mode}", flush=True)'),
    ])

    edit('web/app.js', [
        ("const state={view:'overview',cases:[],stats:{},knowledge:[],active:null,filter:'All'};",
         "const state={view:'overview',cases:[],stats:{},knowledge:[],active:null,filter:'All'};\nlet authToken='';\nlet authIdentity=null;\nconst can=action=>!authIdentity||authIdentity.role==='admin'||(action==='create'||action==='investigate'?authIdentity.role==='analyst':action==='decide'?authIdentity.role==='approver':true);"),
        ("headers:body?{'Content-Type':'application/json'}:{}",
         "headers:{...(body?{'Content-Type':'application/json'}:{}),...(authToken?{'Authorization':'Bearer '+authToken}:{})}"),
        ("'<button class=\"primary\" id=\"newCase\">+ Create case</button>'",
         "(can('create')?'<button class=\"primary\" id=\"newCase\">+ Create case</button>':'')"),
        ("${c.status==='Open'?'<button class=\"primary\" id=\"investigate\">✦ Start agent investigation</button>':''}",
         "${c.status==='Open'&&can('investigate')?'<button class=\"primary\" id=\"investigate\">✦ Start agent investigation</button>':''}"),
        ("${c.status==='Pending approval'?`<div class=\"approval\">", "${c.status==='Pending approval'&&can('decide')?`<div class=\"approval\">"),
        ('value="Demo organization" maxlength="100" required', 'value="${esc(authIdentity?.organization||\'Demo organization\')}" maxlength="100" ${authIdentity?\'readonly\':\'required\'}'),
        ("load().catch(e=>{$('page').innerHTML='<div class=\"warning\">Cannot load the application. Confirm the backend is running: '+esc(e.message)+'</div>';});",
         """async function start(){
  try {
    const config=await req('/api/auth/config');
    if(config.enabled) showLogin();
    else await load();
  } catch(e) { $('page').textContent='Unable to start application: '+e.message; }
}
function showLogin(){
  authToken=''; authIdentity=null;
  $('page').innerHTML=`<section class="panel pad-panel" style="max-width:560px;margin:6vh auto"><h2>Secure local workspace</h2><p>Enter the locally generated access token for your assigned organization. Tokens are kept in memory only.</p><form id="tokenForm"><label for="accessToken">Access token</label><input id="accessToken" type="password" required autocomplete="off" placeholder="Paste your viewer, analyst, approver, or admin token" style="width:100%;padding:14px;margin:12px 0"/><button class="primary" type="submit">Sign in</button></form><p id="loginError" role="alert"></p><small>Local guarded demo — not production SSO</small></section>`;
  $('tokenForm').onsubmit=async event=>{
    event.preventDefault();
    authToken=$('accessToken').value.trim();
    try {
      authIdentity=await req('/api/auth/me');
      await load();
      const profile=document.querySelector('.profile strong');
      if(profile)profile.textContent=authIdentity.name;
      let logout=$('logoutSecure');
      if(!logout){logout=document.createElement('button');logout.id='logoutSecure';logout.textContent='Sign out';logout.className='outline';document.querySelector('.topright').appendChild(logout);logout.onclick=()=>showLogin();}
      notify('Signed in as '+authIdentity.role+' · '+authIdentity.organization);
    } catch(err){authToken='';authIdentity=null;$('loginError').textContent=err.message;}
  };
}
start();"""),
    ])
    edit('.gitignore', [('.env\n', '.env\n.env.*\n')])
    edit('README.md', [
        ('# ElyraOps AI\n', '# ElyraOps AI\n\n**Development update:** Phase 2 provides optional Gemini/PostgreSQL hybrid RAG. Phase 3A adds opt-in **local-only** bearer-token RBAC and scoped case queries. See [SECURITY_PHASE3.md](SECURITY_PHASE3.md) for setup and limitations. This is **not OIDC, PostgreSQL RLS, or production authentication**.\n'),
        ('It does **not** implement autonomous business actions, vector RAG, a Java microservice, Kafka, production auth, or production deployment.', 'It does **not** implement autonomous business actions, a Java microservice, Kafka, production auth, or production deployment.'),
        ('**Important:** This demonstration has **no authentication** or per-tenant authorization. Docker exposes port 8080; run behind private access controls or on your own trusted local machine. Do *not* expose it publicly until those controls are implemented.', '**Important:** The default Docker demo remains unauthenticated. Optional Phase 3A guarded mode needs explicit setup and is not production-ready. Do *not* expose this demo publicly.'),
    ])
    for path, content in PLANNED.items():
        Path(path).write_text(content)
        print('Updated', path)
    print('Phase 3A access controls applied. Run the test suite before enabling guarded mode.')


if __name__ == '__main__':
    main()
