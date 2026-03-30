"""
Query ClinicalTrials.gov API v2 for clinical trials.

API: GET https://clinicaltrials.gov/api/v2/studies
Free, no authentication required. Rate limit ~50 req/min.
"""

import time
import requests
import pandas as pd

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
PAGE_SIZE = 1000
RATE_LIMIT_DELAY = 1.5  # seconds between paginated requests


def query_trials(
    conditions,
    intervention_filter=None,
    statuses=None,
    phases=None,
    sponsor_filter=None,
    max_pages=20,
):
    """
    Query ClinicalTrials.gov API v2 for clinical trials.

    Parameters
    ----------
    conditions : list of str
        Condition terms to search (required). E.g., ["Crohn's Disease", "Ulcerative Colitis"].
    intervention_filter : str or None
        Intervention search term (e.g., "risankizumab").
    statuses : list of str or None
        Trial statuses. Default: all active statuses.
    phases : list of str or None
        Phase filters (e.g., ["PHASE2", "PHASE3"]).
    sponsor_filter : str or None
        Sponsor name search term.
    max_pages : int
        Maximum pages to retrieve (safety limit).

    Returns
    -------
    list of dict
        Flat trial records with keys: nct_id, brief_title, official_title,
        overall_status, phases, lead_sponsor, sponsor_class, conditions,
        interventions, enrollment, start_date, completion_date, study_type,
        countries, arms, collaborators, allocation, masking,
        intervention_model, primary_outcomes, min_age, max_age, sex,
        is_fda_regulated_drug, has_dmc, brief_summary.

    Raises
    ------
    ValueError
        If conditions is empty or None.

    Verification
    ------------
    Prints "✓ Retrieved {N} trials from ClinicalTrials.gov"
    """

    if not conditions:
        raise ValueError("conditions is required — provide a list of disease/condition terms to search.")

    if statuses is None:
        statuses = [
            "RECRUITING",
            "ACTIVE_NOT_RECRUITING",
            "ENROLLING_BY_INVITATION",
            "NOT_YET_RECRUITING",
        ]

    print("\n" + "=" * 70)
    print("QUERYING CLINICALTRIALS.GOV API v2")
    print("=" * 70 + "\n")
    print(f"Conditions: {', '.join(conditions)}")
    print(f"Statuses: {', '.join(statuses)}")
    if intervention_filter:
        print(f"Intervention filter: {intervention_filter}")
    if sponsor_filter:
        print(f"Sponsor filter: {sponsor_filter}")
    if phases:
        print(f"Phase filter: {', '.join(phases)}")
    print()

    # Build base query parameters
    params = _build_query_params(
        conditions, statuses, intervention_filter, phases, sponsor_filter
    )

    # Paginate through results
    all_trials = []
    page_token = None

    for page_num in range(max_pages):
        page_params = dict(params)
        if page_token:
            page_params["pageToken"] = page_token

        print(f"  Fetching page {page_num + 1}...", end=" ")

        try:
            response = requests.get(BASE_URL, params=page_params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"ERROR: {e}")
            if all_trials:
                print(f"  Continuing with {len(all_trials)} trials retrieved so far.")
                break
            raise RuntimeError(f"ClinicalTrials.gov API request failed: {e}") from e

        data = response.json()
        studies = data.get("studies", [])

        extracted = [_extract_trial(s) for s in studies]
        all_trials.extend(extracted)

        total_count = data.get("totalCount", "?")
        print(f"got {len(studies)} studies (total: {total_count})")

        page_token = data.get("nextPageToken")
        if not page_token:
            break

        time.sleep(RATE_LIMIT_DELAY)

    print(f"\n✓ Retrieved {len(all_trials)} trials from ClinicalTrials.gov")
    print("=" * 70 + "\n")

    return all_trials


def _build_query_params(conditions, statuses, intervention_filter, phases, sponsor_filter):
    """Build API query parameters dict."""
    # Condition query: join with OR for broad capture
    cond_query = " OR ".join(f'"{c}"' for c in conditions)

    params = {
        "query.cond": cond_query,
        "filter.overallStatus": ",".join(statuses),
        "pageSize": PAGE_SIZE,
        "countTotal": "true",
        "format": "json",
    }

    if intervention_filter:
        params["query.intr"] = intervention_filter

    if phases:
        params["filter.phase"] = ",".join(phases)

    if sponsor_filter:
        params["query.spons"] = sponsor_filter

    return params


def _extract_trial(study):
    """Extract flat trial record from nested API study object."""
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
    cond_mod = proto.get("conditionsModule", {})
    arms_mod = proto.get("armsInterventionsModule", {})
    design = proto.get("designModule", {})
    contacts_mod = proto.get("contactsLocationsModule", {})
    outcomes_mod = proto.get("outcomesModule", {})
    eligibility_mod = proto.get("eligibilityModule", {})
    oversight_mod = proto.get("oversightModule", {})
    description_mod = proto.get("descriptionModule", {})
    design_info = design.get("designInfo", {})
    masking_info = design_info.get("maskingInfo", {})

    # Extract interventions as list of dicts
    interventions = []
    for intv in arms_mod.get("interventions", []):
        interventions.append({
            "type": intv.get("type", ""),
            "name": intv.get("name", ""),
            "description": intv.get("description", ""),
        })

    # Extract dates safely
    start_date = status_mod.get("startDateStruct", {}).get("date", "")
    completion_date = (
        status_mod.get("primaryCompletionDateStruct", {}).get("date", "")
        or status_mod.get("completionDateStruct", {}).get("date", "")
    )

    # Extract enrollment
    enrollment = design.get("enrollmentInfo", {}).get("count", None)

    # Lead sponsor
    lead_sponsor_info = sponsor_mod.get("leadSponsor", {})

    # Extract countries from locations
    locations = contacts_mod.get("locations", [])
    countries = list(set(loc.get("country", "") for loc in locations if loc.get("country")))

    # Extract arms
    arms = []
    for arm in arms_mod.get("arms", []):
        arms.append({
            "label": arm.get("label", ""),
            "type": arm.get("type", ""),
            "description": arm.get("description", ""),
        })

    # Extract collaborators
    collaborators = []
    for collab in sponsor_mod.get("collaborators", []):
        collaborators.append({
            "name": collab.get("name", ""),
            "class": collab.get("class", ""),
        })

    # Study design fields
    allocation = design_info.get("allocation", "")
    masking = masking_info.get("masking", "")
    intervention_model = design_info.get("interventionModel", "")

    # Primary outcomes
    primary_outcomes = []
    for outcome in outcomes_mod.get("primaryOutcomes", []):
        primary_outcomes.append({
            "measure": outcome.get("measure", ""),
            "timeFrame": outcome.get("timeFrame", ""),
        })

    # Eligibility
    min_age = eligibility_mod.get("minimumAge", "")
    max_age = eligibility_mod.get("maximumAge", "")
    sex = eligibility_mod.get("sex", "")

    # Oversight
    is_fda_regulated_drug = oversight_mod.get("isFdaRegulatedDrug", None)
    has_dmc = oversight_mod.get("oversightHasDmc", None)

    # Brief summary for secondary classification
    brief_summary = description_mod.get("briefSummary", "")

    return {
        "nct_id": ident.get("nctId", ""),
        "brief_title": ident.get("briefTitle", ""),
        "official_title": ident.get("officialTitle", ""),
        "overall_status": status_mod.get("overallStatus", ""),
        "phases": design.get("phases", []),
        "lead_sponsor": lead_sponsor_info.get("name", ""),
        "sponsor_class": lead_sponsor_info.get("class", ""),
        "conditions": cond_mod.get("conditions", []),
        "interventions": interventions,
        "enrollment": enrollment,
        "start_date": start_date,
        "completion_date": completion_date,
        "study_type": design.get("studyType", ""),
        "countries": countries,
        "arms": arms,
        "collaborators": collaborators,
        "allocation": allocation,
        "masking": masking,
        "intervention_model": intervention_model,
        "primary_outcomes": primary_outcomes,
        "min_age": min_age,
        "max_age": max_age,
        "sex": sex,
        "is_fda_regulated_drug": is_fda_regulated_drug,
        "has_dmc": has_dmc,
        "brief_summary": brief_summary,
    }


if __name__ == "__main__":
    # Quick test: fetch a small batch of IBD trials
    trials = query_trials(
        conditions=["Crohn's Disease", "Ulcerative Colitis", "Inflammatory Bowel Disease"],
        max_pages=1,
    )
    print(f"\nSample trial:")
    if trials:
        t = trials[0]
        print(f"  NCT ID: {t['nct_id']}")
        print(f"  Title: {t['brief_title'][:80]}")
        print(f"  Sponsor: {t['lead_sponsor']} ({t['sponsor_class']})")
        print(f"  Status: {t['overall_status']}")
        print(f"  Phases: {t['phases']}")
        print(f"  Interventions: {len(t['interventions'])}")
        for intv in t['interventions'][:3]:
            print(f"    - {intv['type']}: {intv['name']}")
        print(f"  Countries: {', '.join(t['countries'][:5]) or 'N/A'}")
        print(f"  Arms: {len(t['arms'])}")
        for arm in t['arms'][:3]:
            print(f"    - [{arm['type']}] {arm['label']}")
        print(f"  Collaborators: {len(t['collaborators'])}")
        for collab in t['collaborators'][:3]:
            print(f"    - {collab['name']} ({collab['class']})")
        print(f"  Allocation: {t['allocation'] or 'N/A'}")
        print(f"  Masking: {t['masking'] or 'N/A'}")
        print(f"  Intervention model: {t['intervention_model'] or 'N/A'}")
        print(f"  Primary outcomes: {len(t['primary_outcomes'])}")
        for po in t['primary_outcomes'][:3]:
            print(f"    - {po['measure'][:80]} (timeframe: {po['timeFrame']})")
        print(f"  Eligibility: age {t['min_age'] or '?'} - {t['max_age'] or '?'}, sex: {t['sex'] or 'N/A'}")
        print(f"  FDA regulated drug: {t['is_fda_regulated_drug']}")
        print(f"  Has DMC: {t['has_dmc']}")
        print(f"  Brief summary: {t['brief_summary'][:120]}...")

