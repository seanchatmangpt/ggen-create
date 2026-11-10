"""Dry-run probe table for tickets T-001..T-036 (ggen-legacy docs/jira/v26.11.9).

Each entry: id, title, tier (highest tier needed to fully decide), and clauses.
Clauses that need a scratch process (T1) or live backend (T2) are UNVERIFIED until
the operator runs them; the T0 clauses are decided from files on disk.
"""
from __future__ import annotations

from dataclasses import dataclass

from .engine import Clause

CG = "ggen-create:src/ggen_create"
MAN = "ggen-legacy:docs/jira/v26.11.9/manifests"
FE = "srve:servengine-frontend"
PACK = "srve:packs/srve-backend-pack"


def exists(desc, *paths):
    return Clause("exists", desc, {"paths": list(paths)})


def not_exists(desc, *paths):
    return Clause("not_exists", desc, {"paths": list(paths)})


def count(desc, paths, pattern, op, n, exclude=None):
    return Clause("count", desc, {"paths": paths, "pattern": pattern, "op": op, "n": n,
                                  "exclude": exclude})


def distinct(desc, paths, pattern, op, n):
    return Clause("distinct", desc, {"paths": paths, "pattern": pattern, "op": op, "n": n})


def absent(desc, paths, pattern, exclude=None):
    return Clause("absent", desc, {"paths": paths, "pattern": pattern, "exclude": exclude})


def json_len(desc, path, op, n, key=(), where=None):
    args = {"path": path, "op": op, "n": n, "key": list(key)}
    if where:
        args["where"] = list(where)
    return Clause("json_len", desc, args)


def json_required(desc, path, *fields):
    return Clause("json_required", desc, {"path": path, "fields": list(fields)})


def cmd(desc, argv, expect_rc=0, timeout=30):
    return Clause("cmd", desc, {"argv": list(argv), "expect_rc": expect_rc, "timeout": timeout})


def bash_n(script):
    return cmd(f"bash -n {script.split(':', 1)[1]}", ["bash", "-n", "@" + script])


AST = "import ast,sys;ast.parse(open(sys.argv[1]).read())"


def py_parses(script):
    return cmd(f"python parses {script.split(':', 1)[1]}", ["python3", "-c", AST, "@" + script])


def fresh(desc, path, *repos):
    return Clause("fresh", desc, {"path": path, "repos": list(repos)})


def skills(desc, want):
    return Clause("skills", desc, {"want": {k: list(v) for k, v in want.items()}})


def t1(desc, reason):
    return Clause("unverified", desc, {"reason": reason}, tier="T1")


def t2(desc, reason):
    return Clause("unverified", desc, {"reason": reason}, tier="T2")


@dataclass(frozen=True)
class TicketProbe:
    id: str
    title: str
    tier: str
    clauses: tuple[Clause, ...]
    command: str = ""


def _p(n, title, tier, *clauses):
    tid = f"T-{n:03d}"
    return TicketProbe(tid, title, tier, tuple(clauses),
                       f"ggen-create cutover dryrun --ticket {tid}")


WO_FSM = "srve:ontology/work-order-lifecycle.ttl"
SV = "srve:ontology/servengine-current.ttl"
ADMIT = "ggen-legacy:schemas/sunset-admission.schema.json"

PROBES: tuple[TicketProbe, ...] = (
    _p(1, "cutover CLI skeleton", "T0",
       skills("four cutover skills registered with stated authority/confirm",
              {"cutover.plan": ("CONSTRUCT", False), "cutover.power": ("DO_INTENT", True),
               "cutover.verify": ("SELECT", False), "cutover.rollback": ("DO_INTENT", True)}),
       exists("cutover.py present", f"{CG}/cutover.py")),
    _p(2, "receipt chain and sunset schema", "T0",
       json_required("sunset schema requires the four new fields", ADMIT,
                     "predecessor_sha", "release_admission_ref", "replay_digest",
                     "authorization_receipt_ref"),
       exists("dfcm receipt schema present", "home:.claude/dfcm/receipt.schema.json")),
    _p(3, "preflight gate", "T0",
       count("cutover.py defines preflight refusals", [f"{CG}/cutover.py"], r"preflight", "ge", 1)),
    _p(4, "frontend single backend origin", "T0",
       absent("no localhost:4000 in non-test FE source", [f"{FE}/src", f"{FE}/vite.config.ts"],
              r"localhost:4000", exclude=r"\.test\."),
       count("resolver variable referenced", [f"{FE}/src"], r"VITE_BACKEND_ORIGIN", "ge", 1)),
    _p(5, "ontology executable action semantics", "T0",
       count("sv:Action count == 459 (derivation)", [SV], r" a sv:Action\b", "eq", 459),
       count("every action carries a guard predicate", [SV], r"sv:guard", "ge", 459)),
    _p(6, "align one: and sv:; verify against introspection", "T2",
       exists("alignment artifact", "srve:ontology/one-sv-alignment.ttl"),
       t2("counts vs Ash introspection of pinned xaas SHA", "needs mix introspection of xaas")),
    _p(7, "work-order transitions guarded", "T0",
       count("ontology transitions == 48", [WO_FSM], r"^one:\S+ one:transition one:\S+ \.", "eq", 48),
       count("Ash transition() entries == 48",
             ["xaas:lib/xaas/serv_engine/operations/work_order.ex"], r"transition\(", "eq", 48)),
    _p(8, "resource classification manifest", "T0",
       exists("classification manifest", f"{MAN}/resource-classification.json"),
       fresh("manifest matches xaas HEAD", f"{MAN}/resource-classification.json", "xaas")),
    _p(9, "onengine route inventory", "T0",
       exists("route inventory", f"{MAN}/route-inventory.json"),
       fresh("manifest matches onengine-backend HEAD", f"{MAN}/route-inventory.json",
             "srve/onengine-backend")),
    _p(10, "frontend-called action scope", "T0",
       exists("cutover scope file", f"{MAN}/cutover-scope.json"),
       fresh("manifest matches frontend HEAD", f"{MAN}/cutover-scope.json",
             "srve/servengine-frontend")),
    _p(11, "srve DDL census and replay diff", "T1",
       distinct("distinct srve_* tables in migrations", ["xaas:priv/repo/migrations"],
                r"create table\(:srve_[a-z_0-9]+", "eq", 73),
       exists("ddl census", f"{MAN}/ddl-census.json"),
       t1("pg_dump replay diff", "needs scratch Postgres replay of 166 migrations")),
    _p(12, "shared-table tripwire extension", "T0",
       distinct("tripwire names every census table (distinct)",
                ["srve:onengine-backend/src/xaas-contract"], r"srve_[a-z_0-9]+", "ge", 73)),
    _p(13, "prisma coverage and tenant policy", "T0",
       exists("coverage manifest", f"{MAN}/prisma-coverage.json"),
       fresh("manifest matches srve and onengine-backend HEAD", f"{MAN}/prisma-coverage.json",
             "srve/onengine-backend")),
    _p(14, "procurement/dispatch scope decision", "T0",
       exists("scope decision record", f"{MAN}/scope-decisions.md")),
    _p(15, "pack: resources from ontology", "T1",
       exists("pack manifest and resource template", f"{PACK}/pack.toml",
              f"{PACK}/templates/resource.ex.tera"),
       t1("ggen sync run --dry-run twice, byte-stable", "needs ggen over the pack in scratch")),
    _p(16, "pack: migrations", "T1",
       exists("migration template", f"{PACK}/templates/migration.exs.tera"),
       t1("generated DDL equals xaas-migrated DB", "needs scratch Postgres")),
    _p(17, "pack: router and RPC envelope", "T2",
       exists("router template", f"{PACK}/templates/router.ex.tera"),
       t2("290 actions return envelope; fields spec typed 400", "needs candidate running")),
    _p(18, "pack: policies and parity matrix", "T2",
       exists("policy template", f"{PACK}/templates/policy.ex.tera"),
       t2("actor x tenant x action matrix vs recorded xaas", "needs matrix capture from xaas")),
    _p(19, "residue custom handlers", "T0",
       exists("handler registry", f"{PACK}/handlers/registry.toml"),
       count("registry lists the 22 residue handlers", [f"{PACK}/handlers/registry.toml"],
             r"^name = ", "ge", 22)),
    _p(20, "auth and session bridge", "T2",
       exists("auth decision record", f"{MAN}/auth-bridge-decision.md"),
       t2("21 parity cases replayed", "needs candidate running and legacy cases")),
    _p(21, "two-probe identity and CORS", "T2",
       exists("identity globalSetup present", f"{FE}/playwright/globalSetup-xaas-identity.ts"),
       bash_n("srve:scripts/dryrun/two_probe.sh"),
       t2("live probe vs candidate; stub serving /api/health 200 refused", "needs candidate")),
    _p(22, "generated contracts and OpenAPI", "T1",
       not_exists("hand-written contracts removed", f"{FE}/packages/contracts/src/schemas.ts"),
       t1("regenerate contracts in scratch and diff", "needs ggen sync in scratch")),
    _p(23, "ETL write path and vocabulary", "T1",
       exists("etl.ts present", "srve:scripts/etl/etl.ts"),
       count("PRESERVATION_MAP implemented", ["srve:scripts/etl/etl.ts"], r"PRESERVATION_MAP",
             "ge", 1),
       t1("real write into scratch DB; counts and checksums", "needs scratch Postgres")),
    _p(24, "ETL extended aggregates", "T1",
       count("checksumOver flag implemented", ["srve:scripts/etl/etl.ts"], r"checksumOver",
             "ge", 1),
       count("--all flag implemented", ["srve:scripts/etl/etl.ts"], r"--all", "ge", 1),
       t1("~35 aggregates and 15 vocabulary maps of docs/plan/21 implemented",
          "only the flag/engine is checkable from files; aggregate coverage needs a run")),
    _p(25, "HTTP golden court", "T2",
       exists("http golden spec", f"{FE}/playwright/e2e/golden-http-court.spec.ts"),
       t2("passes on xaas, fails on stub", "needs xaas and stub running")),
    _p(26, "backend-neutral seed", "T2",
       exists("seed loader", "srve:scripts/seed_fixture.sh"),
       bash_n("srve:scripts/seed_fixture.sh")),
    _p(27, "golden-court --backend", "T0",
       count("flag implemented", ["srve:bin/golden-court"], r"--backend", "ge", 1),
       bash_n("srve:bin/golden-court")),
    _p(28, "deterministic replay", "T1",
       t1("two scratch generate runs; digest sets and chain head equal",
          "needs ggen sync twice in scratch")),
    _p(29, "independent verifier", "T0",
       exists("verifier present", "ggen-legacy:verifiers/verify_srve_cutover.py"),
       py_parses("ggen-legacy:verifiers/verify_srve_cutover.py")),
    _p(30, "kind scripts parametrized", "T0",
       absent("no xaas:local / deployment/xaas in kind scripts",
              ["srve:scripts/kind-*.sh", "srve:scripts/kind_doctor.sh"],
              r"xaas:local|deployment/xaas"),
       absent("no hashed asset names in smoke test", ["srve:scripts/kind-smoke-test.sh"],
              r"index-[A-Za-z0-9_-]{8}\.(js|css)"),
       bash_n("srve:scripts/kind-bootstrap.sh"), bash_n("srve:scripts/kind-smoke-test.sh"),
       bash_n("srve:scripts/kind_doctor.sh")),
    _p(31, "freeze, delta, switch, rollback", "T0",
       count("cutover.py defines rollback", [f"{CG}/cutover.py"], r"rollback", "ge", 1),
       count("round-trip, drift and all-or-nothing tests exist (not executed by the dry-run)",
             ["ggen-create:tests/test_cutover.py"],
             r"byte_exact|TARGET_DRIFT_REFUSED|all-or-nothing", "ge", 3),
       count("receipt-chain test exists", ["ggen-create:tests/test_cutover.py"],
             r"receipt\.chain\.verify", "ge", 1)),
    _p(32, "side-effect inventory", "T0",
       exists("side-effect table", f"{MAN}/side-effects.md")),
    _p(33, "downstream parity", "T1",
       exists("gymact castle feed test present", "gymact:tests/test_castle_feed.py"),
       t1("candidate-shaped fixtures through igniter and gymact parsers", "needs fixtures")),
    _p(34, "non-core retirement manifest", "T0",
       exists("retirement manifest", f"{MAN}/retirement-manifest.md")),
    _p(35, "sunset is separate actuation", "T0",
       absent("cutover code has no delete/archive path",
              [f"{CG}/cutover.py"], r"rmtree|os\.remove|shutil\.move|\.rmdir|shutil\.make_archive"),
       count("only deletion is the single temp-file cleanup in _atomic_write",
             [f"{CG}/cutover.py"], r"unlink", "le", 1)),
    _p(36, "doctrine and memory updates", "T0",
       absent("backend-law rule no longer mandates xaas",
              ["home:.claude/rules/xaas-servengine-backend-law.md"],
              r"ONLY runtime backend")),
)

BY_ID = {p.id: p for p in PROBES}
