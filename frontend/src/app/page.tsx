"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { components } from "@/lib/api-types";

type Fixture = components["schemas"]["FixtureListItem"];
type Encounter = components["schemas"]["EncounterListItem"];

const WORKFLOW = [
  ["1", "Clinical conversation", "Read the synthetic encounter transcript."],
  ["2", "Extract findings", "Create candidate facts linked to exact transcript text."],
  ["3", "Clinician review", "Approve, edit, or reject each candidate finding."],
  ["4", "Evaluate documentation", "Run configured checks against approved findings."],
  ["5", "Export record", "Create FHIR data from approved findings."],
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
  const [customTranscript, setCustomTranscript] = useState("");
  const [customCheck, setCustomCheck] = useState<"idle" | "invalid" | "valid">("idle");

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

  function checkCustomTranscript() {
    const lines = customTranscript
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const validLines = lines.every((line) => /^(CLINICIAN|PATIENT):\s+\S/i.test(line));
    const speakers = new Set(lines.map((line) => line.split(":", 1)[0].toUpperCase()));
    setCustomCheck(
      lines.length >= 2 && validLines && speakers.has("CLINICIAN") && speakers.has("PATIENT")
        ? "valid"
        : "invalid",
    );
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
              CardioFlow creates candidate clinical findings from a transcript and links each
              finding to its supporting text. A clinician approves, edits, or rejects each
              finding. Notes, configured documentation checks, and exports use approved findings.
            </p>
          </div>
          <div className="service-note">
            <span className="status-dot" aria-hidden="true" />
            Local deterministic demo. No external API.
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
          <strong>Proposed means not yet reviewed.</strong>
          <span>
            A proposed finding is excluded from the note, documentation checks, and export until a
            clinician approves it.
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
                <h3>HFrEF documentation-readiness review</h3>
                <p>
                  Review a synthetic heart-failure encounter, verify findings, inspect nine
                  documentation-readiness checks, and export approved findings as FHIR.
                </p>
                <ul className="demo-details">
                  <li>18 evidence-linked findings</li>
                  <li>Heart rate 64: check not met. Heart rate 78: checks ready.</li>
                  <li>Export contains approved findings</li>
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
                  Review a predefined fictional gastroenterology conversation. Inspect transcript
                  evidence, review findings, generate a note, and inspect supported FHIR output.
                  HFrEF authorization criteria are not applied.
                </p>
              </div>
              <button
                className="btn"
                onClick={() => void create("gerd_simulated")}
                disabled={!canCreate || creatingId !== null || !gerd}
              >
                {creatingId === "gerd_simulated"
                  ? "Opening simulation…"
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
                  Shows uncertain, patient-recalled, and conflicting proposals. These findings
                  stay out of the note, configured checks, and export until reviewed.
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

          <details className="custom-transcript-disclosure">
            <summary>Check a custom synthetic transcript</summary>
            <div className="custom-transcript-boundary">
              <div>
                <strong>Arbitrary extraction is not available in this build.</strong>
                <p>
                  The configured mock extractor only processes the predefined HFrEF, adversarial,
                  and GERD fixtures. This checker validates the speaker format locally. It does not
                  send, save, or extract the entered text.
                </p>
              </div>
              <div className="synthetic-input-warning">
                Use fictional or synthetic information only. Do not enter real patient information.
              </div>
              <label htmlFor="custom-transcript">Synthetic transcript</label>
              <textarea
                id="custom-transcript"
                value={customTranscript}
                onChange={(event) => {
                  setCustomTranscript(event.target.value);
                  setCustomCheck("idle");
                }}
                placeholder={"CLINICIAN: What brings you in today?\nPATIENT: I have a fictional symptom for this demo."}
              />
              <div className="custom-check-row">
                <button
                  className="btn small"
                  type="button"
                  onClick={checkCustomTranscript}
                  disabled={!customTranscript.trim()}
                >
                  Check transcript format
                </button>
                {customCheck === "valid" && (
                  <span className="custom-check valid" role="status">
                    Format recognized. Text was not sent or saved.
                  </span>
                )}
                {customCheck === "invalid" && (
                  <span className="custom-check invalid" role="alert">
                    Add at least one CLINICIAN line and one PATIENT line.
                  </span>
                )}
              </div>
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
                        {encounter.authorization_applicable && encounter.readiness ? (
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
