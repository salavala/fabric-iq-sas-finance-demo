# SAS Finance Intelligence with Microsoft Fabric IQ

An end-to-end, synthetic finance and customer-success demo for a SAS analytics
company. It combines a Microsoft Fabric Lakehouse, managed Delta tables, Fabric
Ontology, Fabric Data Agent, and optional Microsoft Foundry integration through
Model Context Protocol (MCP).

> All companies, people, transactions, forecasts, and financial values in this
> repository are fictional and intended only for demonstrations.

## Business use case

Finance and customer-success teams often make renewal decisions from separate
systems: subscriptions, billing, product telemetry, support, cloud cost, and
forecasting. This demo connects those signals into a semantic model that can
answer questions such as:

- Which customers have declining usage, critical support cases, and renewals in
  the next 90 days?
- Which overdue invoices are associated with at-risk renewals?
- Which accounts have the lowest gross margin after cloud and support costs?
- What explains a customer's renewal forecast?
- What finance and customer-success action should be taken next?

The generated scenario contains healthy, expanding, watch-list, and at-risk
customers. The data reconciles to:

| Metric | Demo value |
|---|---:|
| Active customers | 12 |
| Active subscriptions | 12 |
| Six-month billed revenue | $2,214,000 |
| Six-month cash collected | $2,047,500 |
| Accounts receivable | $166,500 |
| ARR with renewal probability below 60% | $948,000 |

## Architecture

```mermaid
flowchart LR
    G[Deterministic Python generator] --> C[CSV finance data]
    C --> O[Microsoft OneLake]
    O --> N[Fabric PySpark notebook]
    N --> L[Managed Lakehouse Delta tables]
    L --> IQ[Fabric Ontology]
    L --> DA[Fabric Data Agent]
    IQ --> OMCP[Ontology MCP endpoint]
    DA --> DMCP[Data Agent MCP endpoint]
    OMCP --> F[Microsoft Foundry agent]
    DMCP --> F
    F --> U[Finance and customer-success users]
```

`deploy.py` creates or updates the complete Fabric path. Definitions are built
at deployment time so workspace and Lakehouse IDs are never hard-coded.

## Data model

| Table | Purpose |
|---|---|
| `customers` | Customer, industry, geography, segment, and account owner |
| `products` | SAS analytics products and list ARR |
| `subscriptions` | Contract, ARR, licensed users, and renewal date |
| `invoices` | Billing, due dates, payment status, and overdue balances |
| `payments` | Cash receipts by invoice |
| `usage_monthly` | Adoption, active users, compute hours, and production jobs |
| `support_cases` | Severity, status, age, and support effort |
| `cloud_costs` | Compute, storage, and support cost allocation |
| `renewal_forecasts` | Probability, category, reason, and recommended action |
| `customer_finance_summary` | Reconciled executive finance and risk profile |

The ontology contains ten entity types and nine relationships:

```mermaid
erDiagram
    Customer ||--o{ Subscription : owns
    Product ||--o{ Subscription : licensed-by
    Customer ||--o{ Invoice : receives
    Invoice ||--o{ Payment : settled-by
    Subscription ||--o{ UsageMetric : records
    Customer ||--o{ SupportCase : opens
    Subscription ||--o{ CostAllocation : incurs
    Subscription ||--|| RenewalForecast : has
    Customer ||--|| CustomerFinanceProfile : has
```

## Repository contents

```text
.
|-- data/                         # Deterministic synthetic CSV data
|-- fabric/
|   `-- load_finance_tables.py    # Fabric PySpark notebook source
|-- tests/                        # Reconciliation and definition tests
|-- build_assets.py               # Ontology and Data Agent definition builder
|-- deploy.py                     # Idempotent Fabric deployment
|-- generate_data.py              # Synthetic finance data generator
`-- requirements.txt
```

## Run locally

### Prerequisites

- Python 3.11 or later
- No Azure account is required for data generation or tests

### Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Generate a fresh, deterministic dataset:

```powershell
python .\generate_data.py
```

Run the reconciliation and Fabric-definition tests:

```powershell
python -m unittest discover -s .\tests -v
```

The generator writes ten CSV files and `data/quality_report.json`. Re-running it
produces the same business scenarios and totals.

## Deploy to Microsoft Fabric

### Prerequisites

- Azure CLI installed and authenticated
- A Microsoft Fabric workspace on active capacity
- Workspace Contributor or Admin access
- Fabric Ontology and Data Agent preview features enabled for the tenant
- **F64 or higher capacity for the Data Agent MCP runtime**

Ontology can be created on smaller Fabric capacities, but Data Agent MCP calls
return `FTL64 SKU Not Supported` when the workspace uses a trial `FTL64` or a
Fabric SKU below F64.

### 1. Authenticate

Use the tenant and subscription that contain the target Fabric capacity:

```powershell
az login --tenant <tenant-id>
az account set --subscription <subscription-id>
az account show --query "{user:user.name,tenant:tenantId,subscription:id}" -o json
```

### 2. Create or select a Fabric workspace

Create a workspace in the Fabric portal and assign it to F64-or-higher
capacity. Copy the workspace ID from its browser URL:

```text
https://app.fabric.microsoft.com/groups/<workspace-id>/
```

You can also use an existing capacity-backed workspace. Do not use a trial
workspace if you need the Data Agent MCP endpoint.

### 3. Deploy

From the repository root:

```powershell
python .\deploy.py `
  --workspace-id <workspace-id> `
  --workspace-name "<workspace-display-name>"
```

The deployment performs these steps:

1. Regenerates and reconciles all finance data.
2. Creates or reuses `SASFinanceLakehouse`.
3. Uploads CSV files to `Files/raw` in OneLake.
4. Creates or updates `Load SAS Finance Demo`.
5. Runs the notebook to materialize ten managed Delta tables.
6. Validates a Delta transaction log for every table.
7. Creates or updates `SAS_Finance_Customer_Intelligence`.
8. Creates or updates the published `SAS Finance Intelligence Agent`.
9. Writes local `deployment-state.json` with item IDs and MCP endpoints.

The script is idempotent: running it again updates matching items instead of
creating duplicates. `deployment-state.json` and generated tenant-bound
definitions are intentionally ignored by Git.

### 4. Validate in Fabric

Open the target workspace and confirm:

- `SASFinanceLakehouse` contains all ten tables.
- `Load SAS Finance Demo` shows a completed run.
- `SAS_Finance_Customer_Intelligence` contains ten entities and nine
  relationships.
- `SAS Finance Intelligence Agent` is published.

The script also reports row counts, financial reconciliation, Delta validation,
and these MCP endpoint patterns:

```text
https://api.fabric.microsoft.com/v1/mcp/dataPlane/workspaces/{workspaceId}/items/{ontologyId}/ontologyEndpoint

https://api.fabric.microsoft.com/v1/mcp/workspaces/{workspaceId}/dataagents/{dataAgentId}/agent
```

## Demo walkthrough

1. **Start with the finance summary.** Show total ARR, billed revenue, cash
   collection, outstanding AR, and at-risk ARR.
2. **Ask for renewal risk.** Use:
   `Which customers are at risk of renewal, and why?`
3. **Connect operational signals.** Use:
   `Which customers have declining usage and open critical support cases?`
4. **Add financial context.** Use:
   `Which overdue invoices are associated with at-risk renewals?`
5. **Inspect profitability.** Use:
   `Rank customers by gross margin and explain the bottom three.`
6. **Recommend action.** Use:
   `Recommend the next finance and customer-success action for each at-risk customer.`
7. **Show semantic grounding.** In the Ontology, trace Customer to Subscription,
   Invoice, SupportCase, RenewalForecast, and CustomerFinanceProfile.

Expected highlights include:

- **Contoso Health:** declining adoption and an open critical case.
- **Alpine Insurance:** declining usage, overdue AR, and low renewal probability.
- **Tailspin Energy:** softening usage with rising cost pressure.
- **Northstar Bank and Blue Yonder Airlines:** strong expansion candidates.

## Connect to Microsoft Foundry

After deploying a Foundry project and model, add the Fabric IQ knowledge source
or MCP connection using the endpoints from `deployment-state.json`. Configure
the Foundry agent to:

- use Ontology for entity/relationship reasoning,
- use Data Agent for governed analytical queries,
- quantify answers with finance metrics,
- cite the supporting customer, subscription, invoice, usage, support, and
  forecast records,
- state that the data is synthetic.

Fabric IQ, Ontology, Data Agent, and their Foundry integrations are preview
features. Confirm current regional, capacity, tenant-setting, and identity
requirements before production use.

## Security and cleanup

- The repository contains no customer data or credentials.
- Azure access tokens are acquired from Azure CLI and are never written to disk.
- Use least-privilege workspace roles.
- Delete the four demo items or the dedicated workspace when finished to stop
  ongoing capacity usage.

## License

This project is licensed under the MIT License.
