# BLD CRM demonstration scenarios

`seed_crm_demo.py` prepares two existing BLD demonstration requests using the native conversation and proposal store. The first receives a priced proposal and an explicitly recorded **operator demonstration** of customer confirmation. The second receives a priced proposal awaiting review. Existing source orders, catalogue prices and company research remain unchanged.

The script accepts exact order IDs. It requires the Sample Hardware source, `is_demo` on both request and customer, company BLD, website `bld.bg`, and the synthetic contact `purchasing@bld.example`. It preserves the original two article numbers and quantities. Bulgarian labels come from the actual catalogue; custom submitted descriptions are preserved.

| Article | Illustrative final unit price, EUR including VAT |
| --- | ---: |
| 101937 | 9.80 |
| 151077 | 18.50 |

The existing sample request (two of each) totals **€56.60**. The first-phase request (96 of each) totals **€2,716.80**. Proposal notes state: **Демо · примерни крайни цени в EUR с ДДС за представяне на процеса с BLD.** These values describe demonstration proposals, rather than catalogue or agreed commercial prices.

Run from the commissioned demo runtime with its existing source configuration. Use the existing owner principal ID and private state paths. Dry-run is the default:

```sh
python harness/verticals/manufacturer/tools/seed_crm_demo.py \
  --state /absolute/private/workspace \
  --access-state /absolute/private/runtime \
  --environment demo \
  --actor EXISTING_OWNER_PRINCIPAL \
  --confirmed-order EXACT_SAMPLE_ORDER_ID \
  --review-order EXACT_PHASE_ONE_ORDER_ID
```

Review the output, then repeat the command with `--apply --expected-plan-sha256 EXACT_PLAN_SHA256`. The plan hash covers source snapshots, proposal values and target states. Replaying the same plan preserves its proposal versions and timeline events. A changed source or existing differing human proposal requires review.

Each demonstration delivery receives status `demo` in the same transaction that creates its proposal. An active email worker therefore cannot claim it. The script never instantiates an email or paid provider transport. Customer confirmation evidence records `method: operator_demo`, the operator and source hash; it does not represent an actual customer action.

Verification: `harness/tests/test_manufacturer_crm_demo.py` covers dry-run writes, exact totals and Bulgarian catalogue labels, replay, outbound exclusion, original-data preservation, scope/demo/contact validation, changed-source refusal and revoked owner authority. Implementation and tests were prepared offline; live execution belongs to the demo publication step.
