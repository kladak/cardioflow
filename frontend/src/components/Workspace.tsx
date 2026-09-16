"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";
type GeneratedFact = components["schemas"]["Fact"];
type Fact = Omit<GeneratedFact, "candidate"> & {
  candidate?:
    | (NonNullable<GeneratedFact["candidate"]> & { flags: string[] })
    | null;
};
type GeneratedView = components["schemas"]["EncounterView"];
type GeneratedRequirement = GeneratedView["prior_auth"]["requirements"][number];
type View = Omit<GeneratedView, "facts" | "prior_auth"> & {
  facts: Fact[];
  prior_auth: Omit<GeneratedView["prior_auth"], "requirements"> & {
    requirements: Array<
      Omit<GeneratedRequirement, "used_fact_ids" | "pending_fact_ids"> & {
        used_fact_ids: string[];
        pending_fact_ids: string[];
      }
    >;
  };
};
type GeneratedExport = components["schemas"]["ExportDetail"];
type ExportDetail = Omit<GeneratedExport, "bundle" | "excluded"> & {
  bundle: Record<string, any>;
  excluded: NonNullable<GeneratedExport["excluded"]>;
};
type Audit = components["schemas"]["AuditEvent"];
const LABELS: Record<string, string> = {
  hf_diagnosis: "HF diagnosis",
  lvef: "LVEF",
  nyha_class: "NYHA class",
  resting_heart_rate: "Resting heart rate",
  blood_pressure: "Blood pressure",
  cardiac_rhythm: "Cardiac rhythm",
  medication: "Medication",
  beta_blocker_dose_status: "Beta-blocker dose",
  condition_history: "Condition / diagnosis",
  symptom: "Symptom",
};
const GROUPS = [
  {
    title: "Diagnosis & function",
    types: [
      "hf_diagnosis",
      "condition_history",
      "lvef",
      "nyha_class",
      "beta_blocker_dose_status",
    ],
  },
  {
    title: "Vitals & rhythm",
    types: ["blood_pressure", "resting_heart_rate", "cardiac_rhythm"],
  },
  { title: "Medications", types: ["medication"] },
  { title: "Symptoms", types: ["symptom"] },
];
const REQS: Record<string, string> = {
  R1: "Requested medication documented",
  R2: "Prescribed by cardiology",
  R3: "Chronic HFrEF diagnosis",
  R4: "LVEF ≤ 35% within 12 months",
  R5: "NYHA class II–III",
  R6: "Sinus rhythm documented",
  R7: "Resting heart rate ≥ 70 bpm",
  R8: "Beta-blocker optimized",
  R9: "No hypotension",
};
const FLAGS: Record<string, string> = {
  model_low_confidence: "The model marked this low confidence.",
  value_not_in_evidence: "A numeric value does not appear in the quoted text.",
  hedged_language: "The evidence contains hedged language.",
  patient_reported_measurement:
    "Spoken by the patient, not a documented measurement.",
  conflicting_candidates: "Another proposed value conflicts with this one.",
  uncertain_or_hypothetical: "Stated as uncertain or hypothetical.",
  evidence_is_question: "The evidence includes only a question.",
};
function valueOf(f: Fact): any {
  return (f.approved || f.candidate)?.value || {};
}
function summary(f: Fact) {
  const v = valueOf(f);
  switch (f.fact_type) {
    case "lvef":
      return `${v.percent}${v.percent_upper ? `–${v.percent_upper}` : ""}% · ${String(v.modality).replaceAll("_", " ")} · ${v.measured_on_text || "date not stated"}`;
    case "nyha_class":
      return `Class ${v.nyha}${v.nyha_upper ? `–${v.nyha_upper}` : ""}`;
    case "resting_heart_rate":
      return `${v.bpm} bpm`;
    case "blood_pressure":
      return `${v.systolic}/${v.diastolic} mmHg`;
    case "cardiac_rhythm":
      return `${String(v.rhythm).replaceAll("_", " ")} · ${v.source}`;
    case "medication":
      return `${v.raw_name} ${v.dose_text || ""} ${v.frequency}`;
    case "hf_diagnosis":
      return `${v.chronicity} ${String(v.hf_type).toUpperCase()}`;
    case "beta_blocker_dose_status":
      return String(v.status).replaceAll("_", " ");
    case "condition_history":
      return `${String(v.condition).replaceAll("_", " ")} — ${(f.approved || f.candidate)?.assertion}`;
    case "symptom":
      return `${String(v.symptom).replaceAll("_", " ")} — ${(f.approved || f.candidate)?.assertion}`;
    default:
      return JSON.stringify(v);
  }
}
function glyph(f: Fact) {
  return f.review.status === "approved"
    ? f.approved?.edited
      ? "✎✓"
      : "✓"
    : f.review.status === "rejected"
      ? "—"
      : f.candidate?.flags.length
        ? "◐"
        : "○";
}

function reviewLabel(f: Fact) {
  if (f.review.status === "approved")
    return f.approved?.edited ? "APPROVED · EDITED" : "APPROVED";
  if (f.review.status === "rejected") return "REJECTED";
  return f.candidate?.flags.length ? "PROPOSED · FLAGGED" : "PROPOSED";
}

function scrollToEvidence(fact: Fact) {
  const segmentId = (fact.approved || fact.candidate)?.evidence?.[0]?.segment_id;
  if (!segmentId) return;
  document
    .getElementById(`seg-${segmentId}`)
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

export default function Workspace({ id }: { id: string }) {
  const router = useRouter(),
    params = useSearchParams();
  const contentRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View | null>(null),
    [selected, setSelected] = useState<string | null>(params.get("fact")),
    [tab, setTab] = useState(params.get("tab") || "findings"),
    [filter, setFilter] = useState("all"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [edit, setEdit] = useState(false),
    [editText, setEditText] = useState(""),
    [reject, setReject] = useState(false),
    [reason, setReason] = useState(""),
    [exported, setExported] = useState<ExportDetail | null>(null),
    [audit, setAudit] = useState<Audit[] | null>(null);
  const load = useCallback(
    () =>
      api<View>(`/api/encounters/${id}`)
        .then((v) => {
          setView(v);
          setSelected((current) => current || v.facts[0]?.id || null);
          setError("");
          return v;
        })
        .catch((e) => setError(e.message)),
    [id],
  );
  useEffect(() => {
    load();
  }, [load]);
  function navigate(nextTab: string, fact?: string) {
    setTab(nextTab);
    if (fact) setSelected(fact);
    requestAnimationFrame(() => contentRef.current?.scrollTo({ top: 0 }));
    router.replace(
      `/encounters/${id}?tab=${nextTab}${fact ? `&fact=${fact}` : ""}`,
      { scroll: false },
    );
  }
  async function mutate(path: string, body: any) {
    if (!view) return;
    setBusy(true);
    setError("");
    try {
      const v = await api<View>(path, {
        method: "POST",
        body: JSON.stringify({
          ...body,
          expected_revision: view.encounter.revision,
        }),
      });
      setView(v);
      setSelected((current) => current || v.facts[0]?.id || null);
      setEdit(false);
      setReject(false);
      return v;
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function loadAudit() {
    setBusy(true);
    setError("");
    try {
      setAudit(await api<Audit[]>(`/api/encounters/${id}/audit`));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function generateExport() {
    if (!view) return;
    setBusy(true);
    setError("");
    try {
      const detail = await api<ExportDetail>(
        `/api/encounters/${id}/exports`,
        {
          method: "POST",
          body: JSON.stringify({
            expected_revision: view.encounter.revision,
          }),
        },
      );
      setExported(detail);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const selectedFact = view?.facts.find((f) => f.id === selected) || null;
  async function review(action: string) {
    if (!selectedFact) return;
    const body: any = { action };
    if (action === "reject") body.reason = reason;
    if (action === "approve_with_edit") {
      try {
        body.value = JSON.parse(editText);
      } catch {
        setError("The edited value must be valid structured JSON.");
        return;
      }
      body.assertion = (
        selectedFact.approved || selectedFact.candidate
      )?.assertion;
    }
    await mutate(`/api/encounters/${id}/facts/${selectedFact.id}/review`, body);
  }
  const supportsAuthorization =
    view?.encounter.context.fixture_id?.startsWith("hfref") ?? true;
  useEffect(() => {
    if (view && !supportsAuthorization && tab === "authorization") {
      navigate("findings");
    }
  }, [view, supportsAuthorization, tab]);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if ((e.target as HTMLElement).matches("input,textarea,select")) return;
      const facts = view?.facts || [];
      const i = facts.findIndex((f) => f.id === selected);
      if (e.key.toLowerCase() === "j" && facts.length)
        setSelected(facts[Math.min(i + 1, facts.length - 1)].id);
      if (e.key.toLowerCase() === "k" && facts.length)
        setSelected(facts[Math.max(i - 1, 0)].id);
      if (
        e.key.toLowerCase() === "a" &&
        selectedFact?.review.status === "pending"
      )
        review("approve");
      if (
        e.key.toLowerCase() === "r" &&
        selectedFact?.review.status !== "rejected"
      )
        setReject(true);
      const destinations = supportsAuthorization
        ? ["findings", "note", "authorization", "export"]
        : ["findings", "note", "export"];
      if (destinations[Number(e.key) - 1])
        navigate(destinations[Number(e.key) - 1]);
    }
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, [view, selected, selectedFact, supportsAuthorization]);
  if (!view)
    return (
      <main className="home load-state">
        <div className="eyebrow">Encounter workspace</div>
        <h1>{error ? "Encounter unavailable" : "Loading encounter…"}</h1>
        {error && (
          <div className="error" role="alert">
            <p>{error}</p>
            <button className="btn small" onClick={() => void load()}>
              Retry
            </button>
          </div>
        )}
      </main>
    );
  const p = view.encounter.patient,
    c = view.encounter.context;
  const satisfied = view.prior_auth.requirements.filter(
    (r) => r.status === "SATISFIED",
  ).length;
  const reviewed = view.fact_counts.approved + view.fact_counts.rejected;
  const reviewComplete =
    view.fact_counts.total > 0 && reviewed === view.fact_counts.total;
  const currentStage = !view.extraction.latest_run
    ? "extraction"
    : !reviewComplete
      ? "review"
      : supportsAuthorization && tab === "authorization"
        ? "authorization"
        : tab === "export"
          ? "export"
          : tab === "note"
            ? "note"
            : "review";
  return (
    <div className="workspace">
      <header className="topbar">
        <div className="patientline">
          <Link href="/" className="muted">
            ← Encounters
          </Link>
          <strong>
            {p.family_name}, {p.given_name}
          </strong>
          <span className="mono muted">{p.synthetic_mrn}</span>
          <span className="badge">SYNTHETIC</span>
        </div>
        <div className="patientline muted">
          <span>
            {c.visit_type} · {c.encounter_date} · {c.clinician_display}
          </span>
          <button
            className="btn small"
            onClick={() => void loadAudit()}
            disabled={busy}
          >
            Audit
          </button>
        </div>
      </header>
      <div className={`rail ${supportsAuthorization ? "" : "rail-four"}`}>
        <div className="stage complete">
          <span>1. Conversation</span>
          <span className="status">Review the transcript</span>
        </div>
        <div className={`stage ${currentStage === "extraction" ? "current" : "complete"}`}>
          <span>2. Extracted findings</span>
          <span className="status">
            {view.extraction.latest_run
              ? `✓ ${view.fact_counts.total} findings`
              : "Run extraction next"}
          </span>
        </div>
        <div className={`stage ${currentStage === "review" ? "current" : reviewComplete ? "complete" : ""}`}>
          <span>3. Clinician review</span>
          <span className="status">
            {view.fact_counts.total
              ? `${reviewed} of ${view.fact_counts.total} reviewed · ${view.fact_counts.pending_flagged} flagged`
              : "—"}
          </span>
        </div>
        {supportsAuthorization && (
          <div className={`stage ${currentStage === "authorization" ? "current" : ""}`}>
            <span>4. Authorization</span>
            <span className="status">
              Approved evidence · {view.prior_auth.overall.replaceAll("_", " ")} · {satisfied}/9
            </span>
          </div>
        )}
        <div className={`stage ${currentStage === "export" ? "current" : ""}`}>
          <span>{supportsAuthorization ? "5" : "4"}. Export</span>
          <span className="status">
            {view.export.latest
              ? view.export.latest.is_stale
                ? "Out of date"
                : "✓ Generated"
              : view.export.can_export
                ? "Ready to generate"
                : "Blocked"}
          </span>
        </div>
      </div>
      <main className="work">
        <Transcript
          view={view}
          selected={selected}
          onSelect={(id) => {
            setSelected(id);
            navigate("findings", id);
          }}
        />
        <section className="surface">
          {view.extraction.latest_run?.status !== "succeeded" &&
          view.extraction.latest_run?.status !== "succeeded_with_issues" ? (
            <Extract
              view={view}
              busy={busy}
              error={error}
              onRun={() => mutate(`/api/encounters/${id}/extraction-runs`, {})}
            />
          ) : (
            <>
              <nav className="tabs" aria-label="Workspace">
                <button
                  className={`tab ${tab === "findings" ? "active" : ""}`}
                  onClick={() => navigate("findings")}
                >
                  Review findings
                </button>
                <button
                  className={`tab ${tab === "note" ? "active" : ""}`}
                  onClick={() => navigate("note")}
                >
                  Verified note
                </button>
                {supportsAuthorization && (
                  <button
                    className={`tab ${tab === "authorization" ? "active" : ""}`}
                    onClick={() => navigate("authorization")}
                  >
                    Authorization criteria
                  </button>
                )}
                <button
                  className={`tab ${tab === "export" ? "active" : ""}`}
                  onClick={() => navigate("export")}
                >
                  FHIR export
                </button>
              </nav>
              {error && <div className="error">{error}</div>}
              <div className="content" ref={contentRef}>
                <CurrentAction
                  view={view}
                  tab={tab}
                  reviewed={reviewed}
                  supportsAuthorization={supportsAuthorization}
                  onNavigate={navigate}
                />
                {tab === "findings" && (
                  <Findings
                    view={view}
                    selected={selected}
                    filter={filter}
                    setFilter={setFilter}
                    setSelected={setSelected}
                    selectedFact={selectedFact}
                    edit={edit}
                    setEdit={setEdit}
                    editText={editText}
                    setEditText={setEditText}
                    reject={reject}
                    setReject={setReject}
                    reason={reason}
                    setReason={setReason}
                    review={review}
                    busy={busy}
                  />
                )}{" "}
                {tab === "authorization" && (
                  <Authorization
                    view={view}
                    onFact={(x) => navigate("findings", x)}
                  />
                )}{" "}
                {tab === "note" && <Note view={view} mutate={mutate} />}{" "}
                {tab === "export" && (
                  <ExportPane
                    view={view}
                    detail={exported}
                    generate={generateExport}
                    busy={busy}
                  />
                )}
              </div>
            </>
          )}
        </section>
      </main>
      {audit && (
        <aside className="drawer">
          <div className="headline">
            <h2>Audit trail</h2>
            <button className="btn small" onClick={() => setAudit(null)}>
              Close
            </button>
          </div>
          <p className="muted">
            Append-only activity for this synthetic encounter.
          </p>
          {[...audit].reverse().map((a) => (
            <div className="audititem" key={a.id}>
              <div className="eyebrow">
                {new Date(a.at).toLocaleTimeString()} · {a.actor_display}
              </div>
              <strong>{a.summary}</strong>
            </div>
          ))}
        </aside>
      )}
    </div>
  );
}

function CurrentAction({
  view,
  tab,
  reviewed,
  supportsAuthorization,
  onNavigate,
}: {
  view: View;
  tab: string;
  reviewed: number;
  supportsAuthorization: boolean;
  onNavigate: (tab: string, fact?: string) => void;
}) {
  const pending = view.fact_counts.pending;
  const messages: Record<string, [string, string]> = {
    findings: pending
      ? [
          `Review ${pending} proposed ${pending === 1 ? "finding" : "findings"}`,
          "Select a row, compare it with the highlighted transcript sentence, then approve, edit, or reject it.",
        ]
      : [
          "Review complete",
          supportsAuthorization
            ? "All findings have a clinician decision. Inspect how approved evidence changes the authorization result."
            : "All findings have a clinician decision. Inspect the verified note or create a structured export.",
        ],
    note: [
      "Inspect the approved-state note",
      "This note is regenerated only from findings a clinician approved; proposed and rejected facts stay out.",
    ],
    authorization: [
      "Trace evidence to the authorization result",
      "Each criterion shows which approved facts were used. Change the approved heart rate to see the result update deterministically.",
    ],
    export: [
      "Export the verified record",
      "FHIR is a standard format for exchanging healthcare data. Only reviewed, approved findings are eligible for this bundle.",
    ],
  };
  const [title, description] = messages[tab] || messages.findings;
  return (
    <div className="current-action" aria-live="polite">
      <div>
        <span className="eyebrow">Current action · {reviewed} reviewed</span>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
      {tab === "findings" && pending === 0 && (
        <button
          className="btn primary small"
          onClick={() => onNavigate(supportsAuthorization ? "authorization" : "note")}
        >
          {supportsAuthorization ? "View authorization result" : "View verified note"} →
        </button>
      )}
    </div>
  );
}

function Extract({
  view,
  busy,
  error,
  onRun,
}: {
  view: View;
  busy: boolean;
  error: string;
  onRun: () => void;
}) {
  const failed = view.extraction.latest_run?.status === "failed";
  return (
    <div className="extract">
      <div className="eyebrow">AI-style extraction · deterministic fixture</div>
      <h1>Turn the transcript into reviewable clinical findings.</h1>
      <p>
        CardioFlow proposes structured facts and anchors every proposal to
        transcript evidence. Nothing becomes authoritative until a clinician
        approves it.
      </p>
      <div className="boundary">
        <strong>Safety boundary</strong>
        <br />
        Proposed state cannot drive downstream workflow logic or FHIR export.
      </div>
      {failed && (
        <div className="error extraction-failure" role="alert">
          <strong>Extraction failed safely</strong>
          <p>The model response could not be used. No findings were created.</p>
          {(view.extraction.latest_run?.issues || []).map((issue, index) => (
            <p className="mono" key={`${issue.kind}-${index}`}>
              {issue.kind.replaceAll("_", " ")}: {issue.message}
            </p>
          ))}
        </div>
      )}
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      <p className="mono">Provider: Mock · no external API</p>
      <button className="btn primary" onClick={onRun} disabled={busy}>
        {busy ? "Extracting…" : failed ? "Retry extraction" : "Run extraction"}
      </button>
    </div>
  );
}

function Transcript({
  view,
  selected,
  onSelect,
}: {
  view: View;
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  const selectedSegments = new Set(
    view.facts
      .filter((fact) => fact.id === selected)
      .flatMap((fact) => (fact.approved || fact.candidate)?.evidence || [])
      .map((evidence) => evidence.segment_id),
  );
  return (
    <aside className="transcript">
      <div className="panehead">
        <h2>Conversation transcript</h2>
        <span className="mono muted">
          {view.transcript.segments.length} turns · selected evidence highlighted
        </span>
      </div>
      <div className="scroll segments">
        {view.transcript.segments.map((seg) => (
          <div
            className={`segment ${seg.speaker} ${selectedSegments.has(seg.id) ? "selected-evidence" : ""}`}
            id={`seg-${seg.id}`}
            key={seg.id}
          >
            <div className="speaker">
              <span>
                {seg.speaker_label} · {seg.speaker}
              </span>
              <span className="mono">{seg.id}</span>
            </div>
            <p>
              {renderMarked(
                seg.text,
                view.facts
                  .filter((f) => f.review.status !== "rejected")
                  .flatMap((f) =>
                    ((f.approved || f.candidate)?.evidence || [])
                      .filter((e) => e.segment_id === seg.id)
                      .map((e) => ({
                        ...e,
                        factId: f.id,
                        status: f.review.status,
                      })),
                  ),
                selected,
                onSelect,
              )}
            </p>
          </div>
        ))}
      </div>
    </aside>
  );
}
function renderMarked(
  text: string,
  marks: any[],
  selected: string | null,
  onSelect: (id: string) => void,
) {
  if (!marks.length) return text;
  const bounds = [
    0,
    text.length,
    ...marks.flatMap((m) => [m.char_start, m.char_end]),
  ]
    .sort((a, b) => a - b)
    .filter((n, i, a) => i === 0 || n !== a[i - 1]);
  return bounds.slice(0, -1).map((s, i) => {
    const e = bounds[i + 1],
      active = marks.filter((m) => m.char_start <= s && m.char_end >= e);
    const chunk = text.slice(s, e);
    if (!active.length) return <span key={s}>{chunk}</span>;
    const m = active.find((m) => m.factId === selected) || active[0];
    return (
      <button
        type="button"
        key={s}
        className={`evidence ${m.status} ${active.some((m) => m.factId === selected) ? "selected" : ""}`}
        onClick={() => onSelect(m.factId)}
        aria-label={`Evidence for ${m.status} finding`}
      >
        {chunk}
      </button>
    );
  });
}

function Findings({
  view,
  selected,
  filter,
  setFilter,
  setSelected,
  selectedFact,
  edit,
  setEdit,
  editText,
  setEditText,
  reject,
  setReject,
  reason,
  setReason,
  review,
  busy,
}: any) {
  const filters = ["all", "pending", "flagged", "approved", "rejected"];
  const shown = (f: Fact) =>
    filter === "all" ||
    f.review.status === filter ||
    (filter === "flagged" &&
      f.review.status === "pending" &&
      f.candidate?.flags.length);
  return (
    <>
      {view.extraction.latest_run?.issues.length > 0 && (
        <div
          className="error"
          style={{
            borderLeftColor: "var(--cf-status-review)",
            background: "var(--cf-status-pending-wash)",
          }}
        >
          {view.extraction.latest_run.issues.length} proposals or evidence
          references were discarded during strict validation.
        </div>
      )}
      <div className="filter">
        {filters.map((x) => (
          <button
            key={x}
            className={filter === x ? "active" : ""}
            onClick={() => setFilter(x)}
          >
            {x[0].toUpperCase() + x.slice(1)}{" "}
            {x === "all"
              ? view.fact_counts.total
              : x === "flagged"
                ? view.fact_counts.pending_flagged
                : view.fact_counts[x]}
          </button>
        ))}
        <span className="muted" style={{ marginLeft: "auto", fontSize: 11 }}>
          J/K navigate · A approve · R reject
        </span>
      </div>
      {GROUPS.map((g) => {
        const facts = view.facts.filter(
          (f: Fact) => g.types.includes(f.fact_type) && shown(f),
        );
        return facts.length ? (
          <section className="group" key={g.title}>
            <h3>{g.title}</h3>
            {facts.map((f: Fact) => (
              <div
                className={`finding ${f.review.status} ${selected === f.id ? "selected" : ""}`}
                key={f.id}
              >
                <button
                  className="findingrow"
                  aria-pressed={selected === f.id}
                  onClick={() => {
                    setSelected(f.id);
                    setEdit(false);
                    setReject(false);
                    scrollToEvidence(f);
                  }}
                >
                  <span className="finding-status">
                    <span className={`review-label ${f.review.status}`}>
                      <span className="glyph" aria-hidden="true">
                        {glyph(f)}
                      </span>
                      {reviewLabel(f)}
                    </span>
                    <span className="source">
                      {f.origin === "clinician"
                        ? "Clinician entered"
                        : `${f.candidate?.evidence?.[0]?.speaker || "source"} · ${f.candidate?.evidence?.[0]?.segment_id || ""}`}
                    </span>
                  </span>
                  <span className="finding-copy">
                    <strong>{LABELS[f.fact_type]}</strong>
                    <span className="value">{summary(f)}</span>
                  </span>
                  <span className="row-action">Inspect evidence →</span>
                </button>
                {selected === f.id && (
                  <div className="detail">
                    <div className={`state-boundary ${f.review.status}`}>
                      <strong>{reviewLabel(f)}</strong>
                      <span>
                        {f.review.status === "approved"
                          ? "Approved state can inform downstream workflow and export."
                          : f.review.status === "rejected"
                            ? "Rejected state remains excluded from downstream workflows and export."
                            : "Proposed state cannot inform downstream workflows or export."}
                      </span>
                    </div>
                    {f.candidate?.flags.length ? (
                      <div className="flag-callout">
                        <strong>Why this was flagged</strong>
                        <p>
                          This proposal remains excluded until a clinician makes an explicit decision.
                        </p>
                        <ul className="flags">
                          {f.candidate.flags.map((x: string) => (
                            <li key={x}>{FLAGS[x]}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <div className="evidence-heading">
                      <div>
                        <h4>Source evidence</h4>
                        <p>
                          This exact transcript span supports the proposed value.
                        </p>
                      </div>
                      <span className="evidence-link">Linked in transcript</span>
                    </div>
                    {(f.approved || f.candidate)?.evidence?.map((e: any) => (
                      <button
                        type="button"
                        className="quote"
                        key={`${e.segment_id}-${e.char_start}`}
                        onClick={() => scrollToEvidence(f)}
                      >
                        <span className="eyebrow">
                          {e.speaker} · transcript turn {e.segment_id.replace("s", "")}
                        </span>
                        <p>“{e.quote}”</p>
                        <span className="quote-action">Show in transcript ↑</span>
                      </button>
                    ))}
                    {edit ? (
                      <>
                        <h4 style={{ marginTop: 14 }}>Edit structured value</h4>
                        <TypedFactForm
                          fact={f}
                          serializedValue={editText}
                          onChange={setEditText}
                        />
                        <div className="actions">
                          <button
                            className="btn primary small"
                            onClick={() => review("approve_with_edit")}
                          >
                            Save and approve
                          </button>
                          <button
                            className="btn small"
                            onClick={() => setEdit(false)}
                          >
                            Cancel
                          </button>
                        </div>
                      </>
                    ) : null}
                    {!edit && (
                      <div className="actions">
                        {f.review.status === "pending" && (
                          <button
                            className="btn primary small"
                            disabled={busy}
                            onClick={() => review("approve")}
                          >
                            {f.candidate?.flags.length
                              ? "Approve flagged finding"
                              : "Approve"}{" "}
                            <span className="mono">A</span>
                          </button>
                        )}
                        {f.review.status !== "rejected" && (
                          <button
                            className="btn small"
                            onClick={() => {
                              setEdit(true);
                              setEditText(JSON.stringify(valueOf(f), null, 2));
                            }}
                          >
                            Edit
                          </button>
                        )}
                        {f.review.status !== "rejected" && (
                          <button
                            className="btn danger small"
                            onClick={() => setReject(!reject)}
                          >
                            Reject
                          </button>
                        )}
                        {f.review.status !== "pending" &&
                          f.origin === "extraction" && (
                            <button
                              className="btn small"
                              onClick={() => review("reopen")}
                            >
                              Reopen
                            </button>
                          )}
                      </div>
                    )}
                    {reject && (
                      <div className="rejectbox">
                        <input
                          placeholder="Reason (optional)"
                          value={reason}
                          onChange={(e) => setReason(e.target.value)}
                        />
                        <button
                          className="btn danger small"
                          onClick={() => review("reject")}
                        >
                          Confirm reject
                        </button>
                      </div>
                    )}
                    {!edit && (
                      <details className="technical-details">
                        <summary>Technical details</summary>
                        <dl>
                          <div>
                            <dt>Finding ID</dt>
                            <dd className="mono">{f.id}</dd>
                          </div>
                          {(f.approved || f.candidate)?.evidence?.map((e: any) => (
                            <div key={`technical-${e.segment_id}-${e.char_start}`}>
                              <dt>Evidence offset</dt>
                              <dd className="mono">
                                {e.segment_id}[{e.char_start}:{e.char_end}]
                              </dd>
                            </div>
                          ))}
                        </dl>
                        <h4>Structured value</h4>
                        <pre className="mono structured-value">
                          {JSON.stringify(valueOf(f), null, 2)}
                        </pre>
                        {f.candidate?.rationale && (
                          <p className="muted">
                            <strong>Extraction note:</strong> {f.candidate.rationale}
                          </p>
                        )}
                        {f.approved?.edited && (
                          <p className="muted">
                            <strong>Original proposal:</strong>{" "}
                            {JSON.stringify(f.candidate?.value)}
                          </p>
                        )}
                      </details>
                    )}
                  </div>
                )}
              </div>
            ))}
          </section>
        ) : null;
      })}
    </>
  );
}

const FIELD_OPTIONS: Record<string, string[]> = {
  hf_type: ["hfref", "hfmref", "hfpef", "unspecified"],
  chronicity: ["chronic", "acute", "acute_on_chronic", "unspecified"],
  modality: [
    "echocardiogram",
    "cardiac_mri",
    "nuclear",
    "other",
    "unspecified",
  ],
  nyha: ["I", "II", "III", "IV"],
  nyha_upper: ["I", "II", "III", "IV"],
  rhythm: ["sinus", "atrial_fibrillation", "atrial_flutter", "paced", "other"],
  source: ["ecg", "monitor", "exam", "unspecified"],
  drug: [
    "metoprolol_succinate",
    "carvedilol",
    "bisoprolol",
    "sacubitril_valsartan",
    "lisinopril",
    "losartan",
    "valsartan",
    "spironolactone",
    "eplerenone",
    "dapagliflozin",
    "empagliflozin",
    "furosemide",
    "torsemide",
    "bumetanide",
    "ivabradine",
    "digoxin",
    "other",
  ],
  dose_unit: ["mg", "mcg"],
  frequency: ["daily", "bid", "tid", "qhs", "prn", "other", "unspecified"],
  condition: [
    "atrial_fibrillation",
    "atrial_flutter",
    "sick_sinus_syndrome",
    "third_degree_av_block",
    "permanent_pacemaker",
    "gastroesophageal_reflux_disease",
  ],
  symptom: [
    "dyspnea_on_exertion",
    "orthopnea",
    "paroxysmal_nocturnal_dyspnea",
    "peripheral_edema",
    "fatigue",
    "dizziness",
    "palpitations",
    "chest_pain",
    "heartburn",
    "acid_regurgitation",
    "dysphagia",
    "melena",
    "hematemesis",
    "unintentional_weight_loss",
  ],
};
const NUMERIC_FIELDS = new Set([
  "percent",
  "percent_upper",
  "bpm",
  "systolic",
  "diastolic",
  "dose_value",
]);

function TypedFactForm({
  fact,
  serializedValue,
  onChange,
}: {
  fact: Fact;
  serializedValue: string;
  onChange: (value: string) => void;
}) {
  const value = JSON.parse(serializedValue) as Record<string, unknown>;
  const setField = (field: string, raw: string) => {
    const next = { ...value };
    next[field] =
      raw === "" ? null : NUMERIC_FIELDS.has(field) ? Number(raw) : raw;
    onChange(JSON.stringify(next));
  };
  return (
    <div className="factform" aria-label={`Edit ${LABELS[fact.fact_type]}`}>
      {Object.entries(value).map(([field, current]) => {
        const options =
          field === "status"
            ? fact.fact_type === "medication"
              ? ["active", "planned", "discontinued", "held"]
              : [
                  "at_max_tolerated_dose",
                  "below_max_tolerated_dose",
                  "contraindicated",
                  "not_tolerated",
                ]
            : FIELD_OPTIONS[field];
        const range =
          field === "bpm"
            ? [20, 250]
            : field === "systolic"
              ? [50, 260]
              : field === "diastolic"
                ? [20, 160]
                : field.startsWith("percent")
                  ? [5, 85]
                  : [0, undefined];
        return (
          <label key={field}>
            <span>{field.replaceAll("_", " ")}</span>
            {options ? (
              <select
                value={current == null ? "" : String(current)}
                onChange={(event) => setField(field, event.target.value)}
              >
                {current == null && <option value="">Not stated</option>}
                {options.map((option) => (
                  <option key={option} value={option}>
                    {option.replaceAll("_", " ")}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type={NUMERIC_FIELDS.has(field) ? "number" : "text"}
                min={NUMERIC_FIELDS.has(field) ? range[0] : undefined}
                max={NUMERIC_FIELDS.has(field) ? range[1] : undefined}
                value={current == null ? "" : String(current)}
                placeholder={current == null ? "Not stated" : undefined}
                onChange={(event) => setField(field, event.target.value)}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}

function Authorization({
  view,
  onFact,
}: {
  view: View;
  onFact: (id: string) => void;
}) {
  const outcome = view.prior_auth.overall;
  return (
    <div className="auth">
      <div className="simulated">
        <strong>Simulated policy.</strong> Demonstration criteria written for
        CardioFlow. Not a real insurer&apos;s policy or a coverage
        determination.
      </div>
      <div className={`decision-flow ${outcome.toLowerCase()}`}>
        <div>
          <span>Approved evidence</span>
          <strong>{view.fact_counts.approved} findings</strong>
        </div>
        <b aria-hidden="true">→</b>
        <div>
          <span>Simulated criteria</span>
          <strong>9 deterministic checks</strong>
        </div>
        <b aria-hidden="true">→</b>
        <div className="decision-outcome">
          <span>Current outcome</span>
          <strong>{outcome.replaceAll("_", " ")}</strong>
        </div>
      </div>
      <div className="headline">
        <div>
          <div className="eyebrow">Ivabradine · simulated criteria v1.0.0</div>
          <h2
            className={
              view.prior_auth.overall === "READY"
                ? "ready"
                : view.prior_auth.overall === "NOT_MET"
                  ? "notmet"
                  : "incomplete"
            }
          >
            {view.prior_auth.overall === "READY"
              ? "Ready — all 9 criteria documented"
              : view.prior_auth.overall === "NOT_MET"
                ? "Not met by approved findings"
                : "Documentation is incomplete"}
          </h2>
        </div>
        <span className="mono muted">
          review rev {view.encounter.review_revision}
        </span>
      </div>
      <div className="requirements">
        {view.prior_auth.requirements.map((r) => (
          <div
            className={`requirement ${r.requirement_id === "R7" ? "heart-rate-rule" : ""}`}
            data-testid={`requirement-${r.requirement_id}`}
            key={r.requirement_id}
          >
            <span className={`statusword ${r.status}`}>
              {r.status === "SATISFIED"
                ? "✓ Satisfied"
                : r.status === "MISSING"
                  ? "○ Missing"
                  : r.status === "NOT_MET"
                    ? "✕ Not met"
                    : "! Needs review"}
            </span>
            <strong>{REQS[r.requirement_id]}</strong>
            <div>
              <p>{r.explanation}</p>
              {r.used_fact_ids.map((id) => (
                <button
                  className="chip approved-chip"
                  key={id}
                  onClick={() => onFact(id)}
                  title="Open the approved finding and its transcript evidence"
                >
                  {summary(view.facts.find((f) => f.id === id)!)}
                </button>
              ))}
              {r.pending_fact_ids.map((id) => (
                <button
                  className="chip pending-chip"
                  key={id}
                  onClick={() => onFact(id)}
                  title="Review the proposed finding before it can be used"
                >
                  Review candidate →
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Note({
  view,
  mutate,
}: {
  view: View;
  mutate: (path: string, body: any) => Promise<any>;
}) {
  return (
    <div className="notegrid">
      <div className="headline">
        <div>
          <div className="eyebrow">Derived only from approved findings</div>
          <h2>Clinical note</h2>
        </div>
      </div>
      {view.note_sections.map((s) => (
        <section className="notesection" key={s.key}>
          <div className="headline">
            <h3>
              {s.title}{" "}
              <span className="tag">
                {s.accepted
                  ? s.acceptance_stale
                    ? "Accepted · findings changed"
                    : "Accepted"
                  : s.is_overridden
                    ? "Edited"
                    : "Generated"}
              </span>
            </h3>
            <button
              className="btn small"
              onClick={() =>
                mutate(
                  `/api/encounters/${view.encounter.id}/note-sections/${s.key}`,
                  { action: "accept" },
                )
              }
            >
              Accept
            </button>
          </div>
          {s.effective_text ? (
            <pre>{s.effective_text}</pre>
          ) : (
            <p className="muted">
              <em>No approved findings for this section yet.</em>
            </p>
          )}
        </section>
      ))}
    </div>
  );
}

function ExportPane({
  view,
  detail,
  generate,
  busy,
}: {
  view: View;
  detail: ExportDetail | null;
  generate: () => Promise<void>;
  busy: boolean;
}) {
  const active = detail;
  function download() {
    if (!active) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(active.bundle, null, 2)], {
        type: "application/fhir+json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `cardioflow-${active.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="export">
      <div className="eyebrow">Approved-state boundary</div>
      <h2>FHIR R4 export</h2>
      <p className="muted">
        Verified findings can be exported in a standard format used for
        exchanging healthcare data. Authorization readiness is not required,
        and the clinical note is not included in this bundle.
      </p>
      <div className="export-boundary">
        <div>
          <span>Included</span>
          <strong>{view.fact_counts.approved} approved</strong>
        </div>
        <div>
          <span>Excluded</span>
          <strong>{view.fact_counts.pending} proposed</strong>
        </div>
        <div>
          <span>Excluded</span>
          <strong>{view.fact_counts.rejected} rejected</strong>
        </div>
      </div>
      <ul className="checklist">
        <li>
          {view.fact_counts.pending === 0 ? "✓" : "○"} All findings reviewed{" "}
          {view.fact_counts.pending
            ? `— ${view.fact_counts.pending} pending`
            : ""}
        </li>
        <li>
          {view.fact_counts.approved > 0 ? "✓" : "○"} At least one approved
          finding
        </li>
      </ul>
      {!active && (
        <button
          className="btn primary"
          disabled={!view.export.can_export || busy}
          onClick={generate}
        >
          {busy ? "Generating…" : "Generate FHIR bundle"}
        </button>
      )}
      {active && (
        <>
          <div className="headline">
            <h2 className="ready">FHIR R4 bundle generated</h2>
            <div>
              <button className="btn small" onClick={download}>
                Download JSON
              </button>
            </div>
          </div>
          <p>
            {active.bundle.entry?.length || 0} resources ·{" "}
            {active.excluded.length} approved findings intentionally excluded.
          </p>
          <div className="simulated">
            <strong>Text-only concepts.</strong> External terminology codes are
            omitted until verified.
          </div>
          {active.excluded.length > 0 && (
            <details className="mapping-exclusions">
              <summary>
                View {active.excluded.length} explicit mapping exclusions
              </summary>
              <ul>
                {active.excluded.map((item) => (
                  <li key={item.fact_id}>
                    <span className="mono">{item.fact_id}</span> — {item.reason}
                  </li>
                ))}
              </ul>
            </details>
          )}
          <details className="bundle-details">
            <summary>View structured FHIR JSON</summary>
            <pre className="json">{JSON.stringify(active.bundle, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );
}
