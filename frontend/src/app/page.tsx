"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";

type Fixture = components["schemas"]["FixtureListItem"];
type Encounter = components["schemas"]["EncounterListItem"];

const WORKFLOW = [
  ["1", "Clinical conversation", "Read the synthetic encounter transcript."],
  ["2", "Extract findings", "Propose structured facts from the conversation."],
  ["3", "Verify against transcript", "Inspect the source, then approve, edit, or reject."],
  ["4", "Evaluate workflow", "Use approved evidence in deterministic criteria."],
  ["5", "Export verified record", "Create a standard FHIR record from approved state."],
];

function messageOf(error: unknown) {
  return error instanceof Error ? error.message : "The request could not be completed.";
}

export default function Home() {
  const router = useRouter();
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [createError, setCreateError] = useState("");
  const [creatingId, setCreatingId] = useState<string | null>(null);
  const [simulationMode, setSimulationMode] = useState<"predefined" | "brief">("predefined");
  const [scenarioBrief, setScenarioBrief] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [nextFixtures, nextEncounters] = await Promise.all([
        api<Fixture[]>("/api/fixtures"),
        api<Encounter[]>("/api/encounters"),
      ]);
      setFixtures(nextFixtures);
      setEncounters(nextEncounters);
    } catch (error) {
      setLoadError(messageOf(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(fixtureId: string) {
    setCreatingId(fixtureId);
    setCreateError("");
    try {
      const encounter = await api<{ encounter: { id: string } }>("/api/encounters", {
        method: "POST",
        body: JSON.stringify({ fixture_id: fixtureId }),
      });
      router.push(`/encounters/${encounter.encounter.id}`);
    } catch (error) {
      setCreateError(messageOf(error));
    } finally {
      setCreatingId(null);
    }
  }

  const golden = fixtures.find((fixture) => fixture.id === "hfref_golden");
  const adversarial = fixtures.find((fixture) => fixture.id === "hfref_ambiguous");
  const gerd = fixtures.find((fixture) => fixture.id === "gerd_simulated");
  const canCreate = !loading && !loadError;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">CardioFlow</div>
        <div className="notice">Synthetic data only. Not for clinical use.</div>
      </header>
      <main className="home">
        <section className="home-intro" aria-labelledby="page-title">
          <div>
            <div className="eyebrow">Clinical evidence review</div>
            <h1 id="page-title">Turn a clinical conversation into verified structured data.</h1>
            <p className="lede">
              CardioFlow extracts clinical facts from a transcript, shows exactly where each fact
              came from, and lets a clinician verify it. Only approved evidence can inform
              downstream workflows or FHIR export.
            </p>
          </div>
          <div className="service-note">
            <span className="status-dot" aria-hidden="true" />
            Local deterministic demo · no external API
          </div>
        </section>

        <ol className="workflow" aria-label="CardioFlow workflow">
          {WORKFLOW.map(([step, title, description]) => (
            <li key={step}>
              <span className="workflow-number">{step}</span>
              <span>
                <strong>{title}</strong>
                <small>{description}</small>
              </span>
            </li>
          ))}
        </ol>

        <div className="trust-boundary">
          <strong>Proposed is not approved.</strong>
          <span>
            Extraction creates reviewable candidates. A clinician must inspect the linked
            transcript evidence before a fact can be used.
          </span>
        </div>

        {loadError && (
          <div className="error error-action" role="alert">
            <div>
              <strong>Local service unavailable</strong>
              <p>{loadError}</p>
            </div>
            <button className="btn small" onClick={() => void load()}>
              Retry connection
            </button>
          </div>
        )}

        <section className="section demo-section" aria-labelledby="demo-title">
          <div className="section-heading">
            <div>
              <div className="eyebrow">Choose a demonstration</div>
              <h2 id="demo-title">Start with a synthetic encounter</h2>
            </div>
            <span className="tag">Fixture-based extraction</span>
          </div>

          <div className="demo-choice-grid">
            <article className="demo-card demo-primary">
              <div className="demo-card-heading">
                <span className="demo-kind">Guided demo</span>
                <span className="state-label ready">Complete workflow</span>
              </div>
              <div>
                <h3>HFrEF authorization review</h3>
                <p>
                  Walk through a complete heart-failure authorization workflow: grounded
                  extraction, clinician review, deterministic criteria, and FHIR export.
                </p>
                <ul className="demo-details">
                  <li>18 evidence-linked findings</li>
                  <li>HR 64 → Not met; HR 78 → Ready</li>
                  <li>Approved-state-only export</li>
                </ul>
              </div>
              <button
                className="btn primary"
                onClick={() => void create("hfref_golden")}
                disabled={!canCreate || creatingId !== null || !golden}
              >
                {creatingId === "hfref_golden" ? "Opening encounter…" : "Open guided HFrEF demo"}
              </button>
            </article>

            <article className="demo-card simulation-card">
              <div className="demo-card-heading">
                <span className="demo-kind">Simulated encounter</span>
                <span className="badge">GERD consultation</span>
              </div>
              <div>
                <h3>Structure a synthetic consultation</h3>
                <p>
                  Review a fictional gastroenterology conversation through extraction, evidence
                  grounding, clinician verification, note, and structured export. No
                  authorization policy is implied.
                </p>
              </div>
              <div className="simulation-options" role="group" aria-label="Simulation input">
                <button
                  className={simulationMode === "predefined" ? "active" : ""}
                  onClick={() => setSimulationMode("predefined")}
                >
                  Predefined GERD scenario
                </button>
                <button
                  className={simulationMode === "brief" ? "active" : ""}
                  onClick={() => setSimulationMode("brief")}
                >
                  Describe a scenario
                </button>
              </div>
              {simulationMode === "brief" && (
                <div className="scenario-brief">
                  <label htmlFor="scenario-brief">Synthetic patient situation</label>
                  <textarea
                    id="scenario-brief"
                    value={scenarioBrief}
                    onChange={(event) => setScenarioBrief(event.target.value)}
                    placeholder="Example: Adult with burning after meals and sour taste at night"
                    maxLength={280}
                  />
                  <p>
                    Live transcript generation is not configured. This local demo will load the
                    deterministic GERD fallback; your brief is not used to create clinical facts.
                  </p>
                </div>
              )}
              <button
                className="btn"
                onClick={() => void create("gerd_simulated")}
                disabled={!canCreate || creatingId !== null || !gerd}
              >
                {creatingId === "gerd_simulated"
                  ? "Opening simulation…"
                  : simulationMode === "brief"
                    ? "Open deterministic fallback"
                    : "Open simulated GERD encounter"}
              </button>
            </article>
          </div>

          <details className="adversarial-disclosure">
            <summary>Test incomplete and conflicting evidence</summary>
            <div className="adversarial-row">
              <div>
                <strong>{adversarial?.title || "Adversarial HFrEF encounter"}</strong>
                <p>
                  Shows uncertain, patient-recalled, and conflicting proposals that cannot
                  silently become approved state.
                </p>
              </div>
              <button
                className="btn small"
                onClick={() => void create("hfref_ambiguous")}
                disabled={!canCreate || creatingId !== null || !adversarial}
              >
                {creatingId === "hfref_ambiguous"
                  ? "Opening encounter…"
                  : "Open adversarial encounter"}
              </button>
            </div>
          </details>

          {createError && (
            <div className="error" role="alert" aria-live="polite">
              <strong>Encounter could not be opened.</strong> {createError}
            </div>
          )}
        </section>

        <section className="section recent-section" aria-labelledby="recent-title">
          <div className="section-heading">
            <div>
              <div className="eyebrow">Local workspace</div>
              <h2 id="recent-title">Recent encounters</h2>
            </div>
            <span className="muted mono">
              {loading ? "Loading…" : `${encounters.length} total`}
            </span>
          </div>
          {!loading && encounters.length === 0 ? (
            <div className="empty-state">
              <strong>No encounters yet</strong>
              <p>Open the guided demo above to begin the review workflow.</p>
            </div>
          ) : encounters.length > 0 ? (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Patient</th>
                    <th>Date</th>
                    <th>Visit</th>
                    <th>Stage</th>
                    <th>Readiness</th>
                  </tr>
                </thead>
                <tbody>
                  {encounters.map((encounter) => (
                    <tr key={encounter.id}>
                      <td>
                        <button
                          className="table-link"
                          onClick={() => router.push(`/encounters/${encounter.id}`)}
                        >
                          {encounter.patient_display}
                        </button>
                      </td>
                      <td className="mono">{encounter.encounter_date}</td>
                      <td>{encounter.visit_type}</td>
                      <td>{encounter.stage.replaceAll("_", " ")}</td>
                      <td>
                        {encounter.authorization_applicable ? (
                          <span className={`state-label ${encounter.readiness.toLowerCase()}`}>
                            {encounter.readiness.replaceAll("_", " ")}
                          </span>
                        ) : (
                          <span className="muted">Not applicable</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state" aria-live="polite">Loading local encounters…</div>
          )}
        </section>
      </main>
    </div>
  );
}
