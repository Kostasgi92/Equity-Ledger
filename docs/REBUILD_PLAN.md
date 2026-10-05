# Equity Ledger — Ανάλυση & Σχέδιο Επανασχεδιασμού

> Πηγή ανάλυσης: το Replit app `@kostasgi92/Equity-Ledger` (pnpm monorepo: `api-server`, `portfolio-monitor`, `portfolio-mobile`, `lib/*`).
> Στόχος: ίδια λογική και ίδια ροή χρήστη, καθαρότερη αρχιτεκτονική.

---

## 1. Τι κάνει σήμερα η εφαρμογή

Ιδιωτικό «cockpit» μακροπρόθεσμου χαρτοφυλακίου. Νόμισμα αναφοράς **GBP**, κατοχές σε GBP/USD/EUR.

| Περιοχή | Λειτουργικότητα |
|---|---|
| **Auth** | Clerk (sign-in/sign-up). Όλα τα δεδομένα ανήκουν σε έναν χρήστη μέσω `owner_id`. Όταν λήξει το session (401), εμφανίζεται η οθόνη «Session ended» και η cache καθαρίζει. |
| **Overview** | Καθαρή θέση, επενδυμένα κεφάλαια, εκτιμώμενο ετήσιο εισόδημα (από dividend yield), κατανομή ανά asset class, νόμισμα, λογαριασμό και tax wrapper, επίπεδο ρίσκου, πρόσφατη δραστηριότητα. |
| **Holdings** | CRUD κατοχών. Asset classes: equity, etf, fund, crypto, commodity, cash, private_company. Αναζήτηση listing (Yahoo), live ή manual τιμολόγηση, alerts τιμής (άνω/κάτω % από τιμή αναφοράς) με acknowledge. |
| **Investment accounts** | Λογαριασμοί που ξαναχρησιμοποιούνται (πάροχος, τύπος, tax wrapper, pension type, base currency, management style, risk appetite). Η διαγραφή αφήνει τις κατοχές χωρίς λογαριασμό. |
| **Liabilities** | CRUD υποχρεώσεων (υπόλοιπο, επιτόκιο, λήξη). |
| **Recurring** | Επαναλαμβανόμενες αγορές (προσθέτουν units με την τρέχουσα τιμή × FX) ή πληρωμές χρέους (μειώνουν το υπόλοιπο· στο 0 το schedule γίνεται «completed»). Συχνότητα: εβδομαδιαία, μηνιαία, τριμηνιαία, ετήσια, με clamping στο τέλος του μήνα. Ιδεμποτέντ μέσω του unique `(schedule_id, due_date)`. |
| **Advisor** | (α) Ερώτηση ελεύθερου κειμένου → πρώτα guardrails (regex για leverage/παράγωγα/prompt injection), μετά Gemini, μετά validation της εξόδου, και σε αποτυχία deterministic fallback. (β) Structured rebalancing review: εύρη ανά asset class, όριο συγκέντρωσης, κόστη και ρευστότητα, flags, snapshots. (γ) Daily global briefing. |
| **News** | Ειδήσεις σχετικές με τα tickers: Yahoo search και RSS (Bloomberg, WSJ, FT, Economist), κατάταξη trusted publishers, dedupe, σελιδοποίηση ανά 6. Επίσης market leaders, crypto radar και crypto sentiment (CoinMarketCap). |
| **Billing** | Stripe subscription (δοκιμή 3 ημερών), checkout, customer portal, status. |
| **Mobile** | Expo Router app με τα ίδια tabs (index, holdings, liabilities, recurring, advisor, news). Το Billing υπάρχει μόνο στο desktop. |

### Ροή χρήστη (διατηρείται ακριβώς)
```
/ (Landing) ──► /sign-up | /sign-in (Clerk)
     │ signed-in
     ▼
/overview ◄─► /holdings ◄─► /liabilities ◄─► /recurring ◄─► /advisor ◄─► /news   (+ /billing μόνο σε desktop)
     │ 401 σε οποιοδήποτε query
     ▼
SessionExpiredScreen ──► signOut ──► /sign-in
```
Σε κάθε αλλαγή route, το focus μεταφέρεται στο `#page-heading` (accessibility).

### UI/UX design system
- **Παλέτα:** ζεστό χαρτί (`--background 43 36% 94%`), βαθύ petrol teal (`--primary 193 39% 25%`), χρυσό/ώχρα (`--accent 38 47% 57%`), κόκκινο σκουριάς για destructive. Υπάρχει και dark theme.
- **Τυπογραφία:** Manrope (UI), Newsreader serif (τίτλοι), DM Mono (eyebrows, labels, αριθμοί).
- **Layout:** σταθερό sidebar 244px (teal) με «Your cockpit» και «Settings», topbar με ημερομηνία, bottom nav στο mobile. Τόνος: «Good portfolios are usually a little boring.»
- **Components:** stat-card (με dark variant), panel, donut κατανομής, activity list, table με ticker-mark, modal, status badges (active/paused/completed/failed), empty states, skeleton loaders, φιλικά error panels («We hit a quiet patch.»).

---

## 2. Βάση δεδομένων (PostgreSQL)

| Πίνακας | Ρόλος | Σημειώσεις |
|---|---|---|
| `portfolio_holdings` | Κατοχές | units/price σε `numeric(18,6)`, alerts %, `price_error`, `price_updated_at`, FK → accounts (set null) |
| `portfolio_investment_accounts` | Λογαριασμοί | στήλες με παλιά ονόματα (`category`→accountType, `tax_wrapper`→classification) |
| `portfolio_holding_price_alert_events` | Ιστορικό alerts | partial unique: ένα «ανοιχτό» alert ανά (holding, direction) |
| `portfolio_fx_rates` | USD/EUR→GBP | κοινό για όλους τους χρήστες |
| `portfolio_liabilities` | Υποχρεώσεις | `balance_gbp`, αν και υπάρχει και στήλη `currency` |
| `portfolio_activity` | Ροή δραστηριότητας | kind: market / recurring / … |
| `portfolio_recurring_schedules` / `_occurrences` | Recurring | unique (schedule, due_date) |
| `portfolio_rebalancing_targets` | Ρυθμίσεις review | JSON αποθηκευμένο ως `text` |
| `portfolio_rebalancing_review_snapshots` | Αποθηκευμένα reviews | `review_json` ως `text` |
| `portfolio_market_data_state` | Lease/lock για refresh | χειροποίητο distributed lock |
| `portfolio_crypto_market_state` | Cache sentiment | `signals` ως `text` |
| `billing_accounts` | owner ↔ Stripe customer | |

## 3. API (`/api`, όλα πίσω από `requireAuth` εκτός του `/healthz`)

```
GET    /healthz
GET    /portfolio/summary
GET|POST          /portfolio/holdings
PATCH|POST|DELETE /portfolio/holdings/{id}            (POST = retry live price)
POST   /portfolio/price-alerts/{id}/acknowledge
GET|POST          /portfolio/investment-accounts
PATCH|DELETE      /portfolio/investment-accounts/{id}
POST   /portfolio/market-data/refresh
GET    /portfolio/market-listings?q=
GET    /portfolio/crypto-intelligence
GET    /portfolio/crypto-market-radar
GET    /portfolio/market-news?publisher&offset&refresh
GET    /portfolio/market-leaders
GET|POST          /portfolio/liabilities
PATCH|DELETE      /portfolio/liabilities/{id}
GET    /portfolio/activity
GET|POST          /portfolio/recurring-schedules
PATCH|DELETE      /portfolio/recurring-schedules/{id}
POST   /portfolio/recurring-schedules/process
GET    /portfolio/recurring-occurrences
POST   /advisor/review
GET|PUT           /advisor/rebalancing-targets
POST   /advisor/rebalancing-review
GET|POST          /advisor/rebalancing-review/snapshots
DELETE /advisor/rebalancing-review/snapshots/{id}
GET    /advisor/daily-global-briefing
GET    /billing/status
POST   /billing/checkout
POST   /billing/portal
```
Οι εξωτερικοί πάροχοι είναι οι Yahoo Finance (quotes, FX `USDGBP=X`, search, news), CoinMarketCap (crypto quotes, fear & greed, radar), RSS feeds, Gemini (`gemini-3-flash-preview`) και Stripe.

---

## 4. Προβλήματα που διορθώνουμε χωρίς να αλλάξει η συμπεριφορά

1. **Ένα route αρχείο-τέρας** (`routes/portfolio.ts`): υπολογισμοί, validation, DB και πάροχοι είναι όλα μαζί. Χωρίζονται σε modules με service και repository.
2. **Τα χρήματα είναι `Number`**: γίνονται πράξεις float πάνω σε `numeric`. Περνάμε σε `decimal.js` και σε ένα κοινό `Money` type.
3. **JSON αποθηκευμένο σε `text`**: γίνεται `jsonb`, με Zod validation στο όριο.
4. **In-memory caches** (quotes, news, radar) δεν δουλεύουν με πολλά instances και χάνονται σε restart. Μπαίνει ένα cache port με Postgres (ή Redis) υλοποίηση.
5. **Χειροποίητο lease lock και refresh μέσα σε requests**: αντικαθίσταται από **pg-boss** (job queue πάνω στην ίδια Postgres) για market refresh, recurring processing και daily briefing.
6. **Hard-coded fallback FX** (0.79 / 0.86): κρατάμε τη συμπεριφορά, αλλά ως ρητή, τεκμηριωμένη ρύθμιση με ένδειξη «stale» στο UI.
7. **Ασυνέπειες ονομάτων** (`category`/`tax_wrapper`, `balance_gbp` + `currency`, Stripe lookup key `harbour_ledger_monthly`): καθαρά ονόματα στο νέο schema, με migration script από τα παλιά δεδομένα.
8. **Guardrail false positives**: το regex `\boptions?\b` μπλοκάρει και το «what are my options?». Η λογική κρατιέται ίδια, αλλά καλύπτεται με tests ώστε τυχόν αλλαγή να γίνει συνειδητά (βλ. ερωτήσεις).
9. **Πολλαπλές πηγές αλήθειας για τα types** (OpenAPI yaml → Orval → Zod → drizzle-zod): γίνεται **μία πηγή**, τα Zod contracts, από τα οποία παράγονται OpenAPI και client.

---

## 5. Προτεινόμενη αρχιτεκτονική

**Stack:** pnpm workspaces και Turborepo · TypeScript 5.9 · Node 24
- **API:** Fastify 5, `fastify-type-provider-zod`, OpenAPI που παράγεται από τα contracts
- **DB:** PostgreSQL, Drizzle ORM και drizzle-kit migrations (όχι `push`)
- **Jobs:** pg-boss
- **Web:** Vite, React 19, TanStack Router (type-safe routes), TanStack Query, Tailwind v4, shadcn/ui, Clerk
- **Mobile:** Expo Router (διατηρείται), μοιράζεται contracts, api-client και domain
- **Tests:** Vitest (unit/integration με Testcontainers Postgres), Playwright (e2e)

**Κανόνας εξαρτήσεων:** `apps → modules → domain`. Το `domain` δεν κάνει I/O. Οι πάροχοι (Yahoo, CMC, Gemini, Stripe) υλοποιούν ports.

### Δομή αρχείων
```
equity-ledger/
├── apps/
│   ├── api/
│   │   ├── src/
│   │   │   ├── main.ts                    # bootstrap (server + worker)
│   │   │   ├── app.ts                     # Fastify instance, plugins, security headers, CORS
│   │   │   ├── config/env.ts              # Zod-validated env
│   │   │   ├── plugins/
│   │   │   │   ├── auth.ts                # Clerk → request.userId (401 αλλιώς)
│   │   │   │   ├── error-handler.ts       # ενιαίο σχήμα σφαλμάτων
│   │   │   │   └── openapi.ts
│   │   │   ├── modules/
│   │   │   │   ├── holdings/              # routes.ts · service.ts · repository.ts
│   │   │   │   ├── accounts/
│   │   │   │   ├── liabilities/
│   │   │   │   ├── price-alerts/
│   │   │   │   ├── recurring/
│   │   │   │   ├── summary/               # net worth, allocation, income, risk
│   │   │   │   ├── activity/
│   │   │   │   ├── market/                # refresh, listings, leaders, crypto, news
│   │   │   │   ├── advisor/               # review (AI), rebalancing, snapshots, briefing
│   │   │   │   └── billing/
│   │   │   ├── providers/                 # adapters που υλοποιούν ports
│   │   │   │   ├── yahoo/                 # quotes, fx, search, news
│   │   │   │   ├── coinmarketcap/
│   │   │   │   ├── rss/
│   │   │   │   ├── gemini/
│   │   │   │   └── stripe/
│   │   │   ├── jobs/                      # pg-boss: market-refresh, recurring-process, daily-briefing
│   │   │   └── infra/cache.ts             # Cache port (pg/redis)
│   │   └── test/                          # integration (Testcontainers)
│   ├── web/
│   │   ├── src/
│   │   │   ├── main.tsx
│   │   │   ├── routes/                    # TanStack Router (file-based)
│   │   │   │   ├── __root.tsx             # Clerk, QueryClient, SessionExpiryGuard, focus
│   │   │   │   ├── index.tsx              # Landing / redirect
│   │   │   │   ├── sign-in.$.tsx · sign-up.$.tsx
│   │   │   │   └── _app/                  # protected layout (PortfolioShell)
│   │   │   │       ├── overview.tsx · holdings.tsx · liabilities.tsx
│   │   │   │       ├── recurring.tsx · advisor.tsx · news.tsx · billing.tsx
│   │   │   ├── features/                  # UI ανά domain: components + hooks
│   │   │   │   ├── overview/ holdings/ accounts/ liabilities/
│   │   │   │   ├── recurring/ advisor/ news/ billing/
│   │   │   ├── components/
│   │   │   │   ├── layout/                # PortfolioShell, PageHeading, MobileNav
│   │   │   │   ├── feedback/              # LoadingPanel, ErrorPanel, EmptyState, SessionExpired
│   │   │   │   └── ui/                    # shadcn primitives
│   │   │   ├── lib/                       # format.ts, api.ts (client με auth token)
│   │   │   └── styles/                    # tokens.css (ίδια παλέτα/fonts), app.css
│   │   └── e2e/                           # Playwright
│   └── mobile/                            # Expo Router — ίδια tabs, κοινά packages
├── packages/
│   ├── domain/                            # ΚΑΘΑΡΗ λογική, 100% unit-tested
│   │   ├── money.ts                       # Decimal, Money, FX conversion
│   │   ├── valuation.ts                   # valueInGbp, priceStatus, manual vs live
│   │   ├── summary.ts                     # allocation, income, riskLevel
│   │   ├── recurring.ts                   # addCadence, apply purchase/payment
│   │   ├── price-alerts.ts                # threshold crossing
│   │   ├── rebalancing.ts                 # validateSettings, buildReview, fee estimate
│   │   ├── advisor-policy.ts              # guardrails, output validation, fallback
│   │   └── news-ranking.ts                # trusted publishers, dedupe
│   ├── contracts/                         # Zod schemas = μοναδική πηγή αλήθειας API
│   ├── api-client/                        # typed client + TanStack Query hooks
│   ├── db/                                # Drizzle schema, migrations, seed
│   ├── ui-tokens/                         # χρώματα/typography κοινά web + mobile
│   └── config/                            # tsconfig, eslint, vitest presets
├── scripts/migrate-from-replit.ts         # μεταφορά δεδομένων από το παλιό schema
├── docker-compose.yml                     # postgres για local dev
├── turbo.json · pnpm-workspace.yaml · package.json
└── .github/workflows/ci.yml               # lint, typecheck, test, build
```

---

## 6. Βήματα υλοποίησης

| # | Φάση | Παραδοτέο | Κριτήριο ολοκλήρωσης |
|---|---|---|---|
| 0 | **Θεμέλια** | monorepo, Turborepo, TS/ESLint/Prettier presets, docker-compose Postgres, CI | `pnpm build && pnpm test` πράσινο στο CI |
| 1 | **Domain** | μεταφορά καθαρής λογικής (valuation, recurring, rebalancing, advisor-policy, news ranking) με `decimal.js` | τα tests του Replit (π.χ. `rebalancing-review.test.ts`, `market-data.test.ts`) περνούν, μεταφερμένα 1:1 |
| 2 | **DB & contracts** | Drizzle schema (jsonb, καθαρά ονόματα), migrations, seed, Zod contracts για όλα τα endpoints | συμβατότητα σχήματος με το παλιό API (contract tests) |
| 3 | **API core** | Fastify, auth, error handler, modules: holdings, accounts, liabilities, activity, summary | integration tests ανά endpoint, με owner isolation |
| 4 | **Market & jobs** | Yahoo/CMC adapters, cache port, pg-boss jobs (refresh, recurring), price alerts | ιδεμποτέντ recurring, ένα refresh ανά λεπτό σε όλα τα instances |
| 5 | **Advisor & news** | guardrails, Gemini adapter, fallback, rebalancing review/snapshots, briefing, news | adversarial tests (injection, leverage) και test για έξοδο που δεν περνά validation |
| 6 | **Billing** | Stripe checkout/portal/status, **webhook** για sync συνδρομής | e2e με Stripe test mode |
| 7 | **Web UI** | shell, tokens, όλες οι σελίδες με ίδια ροή, SessionExpiry, route focus | Playwright: landing → sign-in → overview → CRUD → advisor |
| 8 | **Mobile** | Expo σε κοινά packages | jest tests του Replit περνούν |
| 9 | **Μετάπτωση** | `migrate-from-replit.ts`, deploy, cutover | αριθμοί overview ίδιοι παλιό ↔ νέο για τον ίδιο χρήστη |

---

## 7. Ανοιχτές αποφάσεις

1. **Hosting:** Fly.io / Railway / Render (API + worker) με Neon/Supabase Postgres, ή κάτι άλλο;
2. **Mobile app:** ξαναχτίζεται τώρα ή μετά το web;
3. **AI πάροχος:** παραμένει το Gemini ή μεταφορά σε Claude; Το port κάνει την αλλαγή ανώδυνη.
4. **Guardrail regex:** κρατάμε 1:1 (μαζί με το false positive «options») ή το διορθώνουμε;
5. **Δεδομένα:** χρειάζεται μεταφορά των υπαρχόντων δεδομένων από τη βάση του Replit;
