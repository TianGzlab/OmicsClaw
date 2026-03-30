# ClinicalTrials.gov API v2 Reference

## Endpoint

```
GET https://clinicaltrials.gov/api/v2/studies
```

Free, no authentication required. Rate limit ~50 requests/minute.

## Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `query.cond` | string | Condition/disease search | `"Crohn's Disease" OR "Ulcerative Colitis"` |
| `query.intr` | string | Intervention search | `risankizumab` |
| `query.spons` | string | Sponsor name search | `Takeda` |
| `query.locn` | string | Location search | `United States` |
| `query.term` | string | General search | `anti-IL23 IBD` |
| `filter.overallStatus` | string | Comma-separated status filter | `RECRUITING,ACTIVE_NOT_RECRUITING` |
| `filter.phase` | string | Comma-separated phase filter | `PHASE2,PHASE3` |
| `pageSize` | integer | Results per page (max 1000) | `1000` |
| `pageToken` | string | Pagination token from previous response | |
| `countTotal` | boolean | Include total count in response | `true` |
| `format` | string | Response format | `json` or `csv` |
| `sort` | string | Sort order | `LastUpdatePostDate:desc` |

## Status Values

| API Value | Meaning |
|-----------|---------|
| `RECRUITING` | Actively recruiting participants |
| `NOT_YET_RECRUITING` | Not yet started recruiting |
| `ACTIVE_NOT_RECRUITING` | Ongoing but not enrolling |
| `ENROLLING_BY_INVITATION` | Enrolling by invitation only |
| `COMPLETED` | Study completed |
| `TERMINATED` | Stopped early |
| `WITHDRAWN` | Withdrawn before enrollment |
| `SUSPENDED` | Temporarily paused |

## Phase Values

| API Value | Display |
|-----------|---------|
| `EARLY_PHASE1` | Phase 1 |
| `PHASE1` | Phase 1 |
| `PHASE2` | Phase 2 |
| `PHASE3` | Phase 3 |
| `PHASE4` | Phase 4 |
| `NA` | Not Applicable |

Note: A study can have multiple phases (e.g., `["PHASE2", "PHASE3"]` for Phase 2/3 studies).

## Response Structure

```json
{
  "totalCount": 1234,
  "nextPageToken": "...",
  "studies": [
    {
      "protocolSection": {
        "identificationModule": { "nctId": "NCT...", "briefTitle": "...", "officialTitle": "..." },
        "statusModule": {
          "overallStatus": "RECRUITING",
          "startDateStruct": {"date": "2023-01"},
          "primaryCompletionDateStruct": {"date": "2025-06"},
          "completionDateStruct": {"date": "2025-12"}
        },
        "sponsorCollaboratorsModule": {
          "leadSponsor": {"name": "...", "class": "INDUSTRY"},
          "collaborators": [{"name": "...", "class": "OTHER"}]
        },
        "conditionsModule": { "conditions": ["Crohn's Disease"] },
        "armsInterventionsModule": {
          "interventions": [{"type": "DRUG", "name": "...", "description": "..."}],
          "arms": [{"label": "Treatment", "type": "EXPERIMENTAL", "description": "..."}]
        },
        "designModule": {
          "studyType": "INTERVENTIONAL",
          "phases": ["PHASE3"],
          "enrollmentInfo": {"count": 500},
          "designInfo": {
            "allocation": "RANDOMIZED",
            "interventionModel": "PARALLEL",
            "maskingInfo": {"masking": "DOUBLE"}
          }
        },
        "contactsLocationsModule": {
          "locations": [{"country": "United States"}, {"country": "Germany"}]
        },
        "outcomesModule": {
          "primaryOutcomes": [{"measure": "Clinical remission", "timeFrame": "52 weeks"}]
        },
        "eligibilityModule": {
          "minimumAge": "18 Years",
          "maximumAge": "80 Years",
          "sex": "ALL"
        },
        "oversightModule": {
          "isFdaRegulatedDrug": true,
          "oversightHasDmc": true
        },
        "descriptionModule": {
          "briefSummary": "A study of..."
        }
      }
    }
  ]
}
```

## Extracted Modules

The skill extracts data from the following API response modules:

| Module | Fields Extracted | Purpose |
|--------|-----------------|---------|
| `identificationModule` | nctId, briefTitle, officialTitle | Trial identification |
| `statusModule` | overallStatus, startDateStruct, completionDateStruct | Status and timeline |
| `sponsorCollaboratorsModule` | leadSponsor (name, class), collaborators | Sponsor and partnerships |
| `conditionsModule` | conditions | Disease indications |
| `armsInterventionsModule` | interventions (type, name, description), arms (label, type) | Drug classification, comparator analysis |
| `designModule` | phases, enrollmentInfo, studyType, designInfo (allocation, interventionModel, maskingInfo) | Phase, enrollment, study design |
| `contactsLocationsModule` | locations[].country | Geographic analysis |
| `outcomesModule` | primaryOutcomes (measure, timeFrame) | Endpoint comparison |
| `eligibilityModule` | minimumAge, maximumAge, sex | Patient population analysis |
| `oversightModule` | isFdaRegulatedDrug, oversightHasDmc | Regulatory signals |
| `descriptionModule` | briefSummary | Secondary mechanism classification |

## Sponsor Classes

| Value | Meaning |
|-------|---------|
| `INDUSTRY` | Pharmaceutical/biotech company |
| `NIH` | National Institutes of Health |
| `FED` | Other US Federal agency |
| `OTHER` | Academic, hospital, or other |
| `OTHER_GOV` | Non-US government |
| `NETWORK` | Clinical network |
| `INDIV` | Individual investigator |

## Pagination

Results are paginated. Use `nextPageToken` from the response in subsequent requests:

```python
# First request
response = requests.get(BASE_URL, params={"query.cond": "IBD", "pageSize": 1000})
data = response.json()

# Next page
next_token = data.get("nextPageToken")
if next_token:
    response = requests.get(BASE_URL, params={..., "pageToken": next_token})
```

## Rate Limiting

- ~50 requests per minute per IP
- Use 1-2 second delay between paginated requests
- No authentication required
