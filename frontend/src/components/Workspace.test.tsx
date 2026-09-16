import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Workspace from "./Workspace";
import { api } from "@/lib/api";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  api: vi.fn(),
}));

const evidence = {
  segment_id: "s7",
  speaker: "clinician",
  char_start: 21,
  char_end: 23,
  quote: "78",
};

const heartRate = {
  id: "fact_hr",
  fact_type: "resting_heart_rate",
  origin: "extraction",
  candidate: {
    value: { bpm: 78 },
    assertion: "affirmed",
    evidence: [evidence],
    confidence: 0.99,
    flags: [],
    rationale: null,
  },
  approved: {
    value: { bpm: 78 },
    assertion: "affirmed",
    evidence: [evidence],
    edited: false,
    attestation_note: null,
    approved_by: "Dr. A. Reyes",
    approved_at: "2026-09-16T12:00:00Z",
  },
  review: {
    status: "approved",
    reviewed_by: "Dr. A. Reyes",
    reviewed_at: "2026-09-16T12:00:00Z",
    rejection_reason: null,
  },
};

const baseView = {
  encounter: {
    id: "enc_test",
    created_at: "2026-09-16T12:00:00Z",
    updated_at: "2026-09-16T12:00:00Z",
    revision: 2,
    review_revision: 1,
    patient: {
      synthetic_mrn: "SYN-TEST01",
      given_name: "Ellis",
      family_name: "Varga",
      birth_date: "1964-01-01",
      sex: "female",
    },
    context: {
      fixture_id: "hfref_golden",
      encounter_date: "2026-09-16",
      visit_type: "Heart failure follow-up",
      specialty: "cardiology",
      clinician_display: "Dr. A. Reyes",
    },
  },
  stage: "review_complete",
  transcript: {
    segments: [
      {
        id: "s7",
        seq: 7,
        speaker: "clinician",
        text: "Resting heart rate is 78 beats per minute.",
      },
    ],
  },
  extraction: {
    latest_run: {
      id: "run_test",
      provider: "mock",
      model: null,
      prompt_version: "v1",
      started_at: "2026-09-16T12:00:00Z",
      completed_at: "2026-09-16T12:00:01Z",
      attempts: 1,
      status: "succeeded",
      accepted_fact_ids: ["fact_hr"],
      issues: [],
      raw_output: null,
    },
    run_count: 1,
    can_run: false,
    provider: "mock",
  },
  facts: [heartRate],
  fact_counts: {
    total: 1,
    pending: 0,
    pending_flagged: 0,
    approved: 1,
    approved_edited: 0,
    rejected: 0,
  },
  note_sections: [],
  prior_auth: {
    policy_id: "sim-ivabradine-hfref",
    policy_version: "1.1.0",
    review_revision: 1,
    overall: "READY",
    requirements: [
      {
        requirement_id: "R7",
        status: "SATISFIED",
        explanation: "Resting heart rate 78 bpm is at or above 70 bpm.",
        used_fact_ids: ["fact_hr"],
        pending_fact_ids: [],
        missing_fact_types: [],
        context_fields_used: [],
      },
    ],
  },
  authorization_policy: {
    id: "sim-ivabradine-hfref",
    version: "1.1.0",
    simulated: true,
    display_name: "Ivabradine documentation-readiness demonstration",
    payer_display: "CardioFlow demonstration rules",
    disclaimer:
      "This is a simulated documentation-readiness workflow. It does not reproduce a payer policy, determine coverage, or provide clinical guidance.",
    medication: "ivabradine",
    indication_text: "Synthetic test indication.",
    requirements: [
      {
        id: "R7",
        title: "Resting heart rate at or above 70 bpm",
        policy_text: "The approved resting heart rate is 70 beats per minute or higher.",
        evaluator: "heart_rate_at_least",
        params: { min_bpm: 70 },
        fact_types: ["resting_heart_rate"],
        operator: "greater_than_or_equal",
        threshold: 70,
        unit: "bpm",
        provenance_classification: "supported_by_authoritative_source",
        provenance_note: "The FDA prescribing information specifies the threshold.",
        criterion_sources: [
          {
            title: "CORLANOR (ivabradine) prescribing information",
            organization: "U.S. National Library of Medicine DailyMed",
            url: "https://dailymed.nlm.nih.gov/example",
            section: "1.1 Heart Failure in Adult Patients",
            version_or_date: "Revised August 2021",
            source_type: "fda_prescribing_information",
          },
        ],
        last_verified_at: "2026-09-16",
      },
    ],
  },
  export: { can_export: true, blocked_reasons: [], latest: null },
};

const mockedApi = vi.mocked(api);

describe("CardioFlow encounter workspace", () => {
  beforeEach(() => {
    replace.mockReset();
    mockedApi.mockReset();
  });

  it("keeps patient transcript evidence separate from criterion provenance", async () => {
    mockedApi.mockResolvedValue(baseView as never);
    render(<Workspace id="enc_test" />);

    fireEvent.click(await screen.findByRole("button", { name: "Authorization criteria" }));

    expect(screen.getByText("Patient value")).toBeVisible();
    expect(screen.getByText("Patient source: Transcript turn 7 (clinician)")).toBeVisible();
    expect(screen.getByText("Criterion source")).toBeVisible();
    expect(screen.getAllByText("Authoritative source")[0]).toBeVisible();
    expect(
      screen.getAllByRole("link", { name: "CORLANOR (ivabradine) prescribing information" })[0],
    ).toHaveAttribute("href", "https://dailymed.nlm.nih.gov/example");
    expect(screen.getByText("Criterion provenance and rule details")).toBeVisible();
  });

  it("keeps finding technical details available through disclosure", async () => {
    mockedApi.mockResolvedValue(baseView as never);
    render(<Workspace id="enc_test" />);

    expect(await screen.findByText("Technical details")).toBeVisible();
    expect(screen.getByText("Evidence offset")).not.toBeVisible();
    fireEvent.click(screen.getByText("Technical details"));
    expect(screen.getByText("Evidence offset")).toBeVisible();
    expect(screen.getByText("s7[21:23]")).toBeVisible();
  });

  it("does not show HFrEF authorization controls for a GERD encounter", async () => {
    mockedApi.mockResolvedValue({
      ...baseView,
      encounter: {
        ...baseView.encounter,
        context: {
          ...baseView.encounter.context,
          fixture_id: "gerd_simulated",
          specialty: "gastroenterology",
        },
      },
      authorization_policy: null,
    } as never);
    render(<Workspace id="enc_test" />);

    await screen.findByRole("button", { name: "Verified note" });
    expect(screen.queryByRole("button", { name: "Authorization criteria" })).not.toBeInTheDocument();
  });
});
