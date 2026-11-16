# 01 — Loyalist's own content: why customers buy

Scope: 21 blog posts, site pages (`loyalist/txt/`), plus fetched (2026-11-16): Eater "Why Is This Restaurant Emailing Me Like We're Friends?" (eater.com/dining-out/978611/…), PR Newswire seed release (Oct 20 2025), eatloyalist.substack.com (RSS, 10 posts), Magic Ashby board (jobs.ashbyhq.com/magic, 11 roles), loyalist.com/industry-insider-alerts/, /receipts/, robots.txt, sitemap. Raw fetches: `scratchpad/loyalist/ext/`.
Tags: **C** = confirmed with source; **I** = my inference. Abbreviations: `blog/X` = `loyalist/blog/X.md`; `txt/X` = `loyalist/txt/X.txt`.

Heads-up: `txt/careers__software-engineer-data-product.txt` is a **Noetica** job page, not Magic. The real roles are on Ashby (C). `blog/.md` is a 404 page (C).

---

## 0. Headline: Magic published its own signal list

The Founding GTM Engineer posting (Ashby, published 2026-11-04) says: "Score every account on signals like **new openings, chef and GM changes, and groups switching reservation or POS systems**." It also says: "We sell in person. Our team walks into restaurants, hosts dinners for operators, and shows up at the industry's events." (C) It asks for "High competence with Claude and Clay" and for cold email at scale. Takeaway: outbound is just being stood up and the signal taxonomy is already fixed (I).

## 1. Jobs-to-be-done and pains (operators' words first)

| JTBD / pain | Quote | Source | |
|---|---|---|---|
| See a guest across all properties | "track their journey across all our properties" (Kyra Burner, MFG) | txt/customer-stories | C |
| Know regulars, the lapsed and the wine buyers | "who my best regulars are, who has not been back in a while, who loves wines, who comes to special events" (Cedric Nicaise, Noortwyck) | txt/customer-stories | C |
| Personal follow-up instead of business cards | "I personally hate business cards" … "alerts if it's someone's like, third visit … or if they give us a really positive review on Google" (Nicaise) | Eater | C |
| Centralize VIP texts and guest look-up | "centralized VIP line and guest look-up feature have centralized our guest relations" (Mattos) | txt/home | C |
| Prove marketing ROI fast (land-and-expand) | "within two weeks the return … was so undeniably strong … enroll the third restaurant" (Elizabeth Sharp, Glendale) | txt/customer-stories | C |
| Target private-event outreach seasonally | "especially valuable for private events … as we head into the holiday season" (Ellen Yin, High Street) | txt/customer-stories | C |
| First CRM, needs hand-holding | "I hadn't worked with a CRM like Loyalist before joining Grassfed … learning curve painless" (Ellie Jackson) | txt/customer-stories | C |
| Consolidate tools, save time | "simplifies, consolidates, and organizes guest information, reviews, reservations" … "cheat code and a short cut" (Gabriel Stulman, Happy Cooking) | txt/customer-stories | C |
| Scale personal relationships with top regulars | "scale that personal relationship with every guest" (Mario Carbone) | PR Newswire | C |
| Acquisition costs rising, so retain | "The cost of acquiring a new diner is becoming higher than ever" (Maggie Tang) | Eater | C |

Pains in Loyalist's own framing (C unless noted):
- **"Fragmentation Tax"**: "Excel spreadsheets, scribbled notes, and sheer memory" (blog/the-loyalist-manifesto).
- **Knowledge leaves with staff**: "It all lives in one person's head. And when they leave, the context disappears" (blog/the-cookie-for-the-real-world). Also "When that GM leaves, the number, the threads and the guest history leave too" (blog/how-to-set-up-a-vip-communication-channel…).
- **Dirty data**: "the same guest appeared six times with three different email addresses"; "Marketing teams hesitate before every send" (blog/introducing-guestbook-studio-what).
- **Invisible lapsed regulars**: "nobody remembers an absence". One group had "3,434 guests who had been regulars and had quietly stopped coming" (blog/does-your-restaurant-need-a-crm).
- **Group inconsistency**: "One general manager marks people as VIP generously, another almost never does" (same post). The CFO angle is cross-concept guest sharing.
- **Events vs book double-booking**: "two teams are sharing one dining room through a system of remembering". The "weekly audit is the tell" (blog/tripleseat-to-resy).
- **Mailchimp failure modes**: duplicates, stale exports, no attribution, untargeted wine-dinner blasts (blog/mailchimp-alternatives…).
- **Slow event-inquiry replies**: planners contact "ten venues at once"; "a 30-minute delay can cost a booking" (blog/how-can-a-restaurant-group-get-more-private-event-bookings).
- **No laptop, no logins**: "Sometimes our customers don't own a laptop, are on the floor all day" (blog/batteries-included).
- **Data ownership**: "you do not really have a guest list. You have access to one" (blog/does-your-restaurant-need-a-crm).

## 2. Buying triggers and outside observability

| # | Trigger | Evidence | Observable from outside? (source) |
|---|---|---|---|
| 1 | **New venue opening / 2nd location** | GTM Eng job: "new openings" (C). Owner.com compare: "What changes when we open a second location? The memory stops working" (C). Constant Contact compare: "opening a second room does not turn your best guest into two people" (C) | **Yes, strong.** New Resy/OpenTable/SevenRooms/Tock listings; Eater "openings" coverage; state liquor-license applications (NY SLA etc.); building permits; Google Business Profile creation; group website new location page (I) |
| 2 | **New GM / chef change** | GTM Eng: "chef and GM changes" (C). Post dated 2026-11-10, "…first week as a new GM" (C). VIP-line post: "When that GM leaves…" (C) | **Yes.** LinkedIn job changes; job posts for GM/Director of Ops on Culinary Agents, Indeed, Poached; press on chef departures (Eater, Grub Street) (I) |
| 3 | **Switching reservation or POS system** | GTM Eng: "groups switching reservation or POS systems" (C). "Do you have to switch reservation systems…? No" (blog/how-do-you-track…) (C). Eater: Sunn's went Resy to OpenTable (C, not a Loyalist customer) | **Yes.** Booking widget change on the venue site (resy.com / opentable.com / sevenrooms.com / exploretock.com embeds); online-ordering link domain change (toasttab.com, square.site, etc.); BuiltWith or periodic HTML diffs (I) |
| 4 | **Holiday / private-event season (Sep–Dec)** | "Holiday parties are the big one, so build that list in September". Send a note "10 to 12 weeks ahead" (blog/how-can-a-restaurant-group…) (C). Ellen Yin's holiday quote (C). "December buyout" mentioned repeatedly (C) | **Partly.** Seasonal timing is calendar-driven. Venues with a "Private Dining / Events" page or a Tripleseat or Perfect Venue inquiry form are detectable (I) |
| 5 | **Tripleseat + Resy combo (no native sync)** | "Resy OS does not sync Tripleseat events into the book". Running since Q2 2026 "up to groups doing seven and eight figures a year in event revenue" (blog/tripleseat-to-resy) (C) | **Yes, high-precision.** A Resy widget plus a Tripleseat lead form (tripleseat.com/… embed) on the same site. OpenTable and SevenRooms already have native Tripleseat sync, so those combos rank lower (C/I) |
| 6 | **Multi-concept or multi-property group** (incl. hotel + restaurant + club) | "This is where it stops being optional" (blog/does-your-restaurant-need-a-crm) (C). Most compare pages: "one room to fifty locations" (C) | **Yes.** Group website listing several concepts; shared ownership in press; same booking-account patterns across venues (I) |
| 7 | **Outgrowing Mailchimp / Constant Contact** | "Someone is exporting the POS every month, merging duplicates" (txt/compare__mailchimp) (C) | **Partly.** Mailchimp signup forms (list-manage.com) or Constant Contact forms on the site; footer newsletter embeds (I) |
| 8 | **Marketing hire / first CRM owner** | Day-to-day owner is "one person who already owns marketing or guest relations" (txt/compare) (C). Grassfed quote "before joining Grassfed" (C) | **Yes.** Job posts for Marketing Manager, Guest Relations, CRM Manager or Director of Events at groups (I) |
| 9 | **Events inquiry volume growth** | OpenTable says private-dining inquiries "more than doubled last year" (cited in 3 posts) (C) | **Partly.** Events pages, published buyout minimums, event-sales job posts (I) |
| 10 | **Review volume or crisis** | Review inbox with AI replies. "3 million+ reviews in Loyalist" (blog/best-restaurant-review…) (C) | **Yes.** Google/Yelp review velocity and rating drops; no owner replies (I) |
| 11 | **Hotel adds F&B or restaurant inside a hotel** | Journeys spa-to-lunch example; PMS integrations; Akia compare (C) | **Yes.** Hotel openings (STR/press), hotel restaurant on Resy/OpenTable, PMS booking engine on site (I) |
| 12 | **Michelin / press recognition** | "15% of US Michelin-starred restaurants" are customers (blog/mailchimp-alternatives) (C). The Insider Alerts agent targets press-sensitive rooms (C) | **Yes.** Michelin and Beard lists, Eater 38 lists (I) |

## 3. Status-quo alternatives (/compare/ pages)

| Alternative | Category | Buyer implied | Detectable on venue site? |
|---|---|---|---|
| Mailchimp | Email | Single venue or small group, newsletter-only, manual POS exports (C) | Yes. list-manage.com / mc.us forms, chimpstatic.com script (I) |
| Constant Contact | Email | "One room sending a monthly newsletter", $12/mo (C) | Yes. ctctcdn / constantcontact forms (I) |
| Klaviyo | Email/SMS | Venue with real ecommerce (merch, gift cards, meal kits). Now reads OpenTable (C) | Yes. klaviyo.js / static.klaviyo.com (I) |
| Bloom Intelligence | WiFi guest data | Counter-service chain, passive WiFi capture (C) | Partly. Captive portal, not the site (I) |
| Thanx | Loyalty | Points program run as system of record (C) | Yes. Thanx app links / rewards page (I) |
| Paytronix (also integration) | Loyalty + gift | Points, tiers, gift cards at scale (C) | Yes. Paytronix gift/loyalty portal links (I) |
| Punchh | Loyalty | QSR/fast casual where "the app is the relationship" (C). Poor fit (I) | Yes. App-store links, Punchh-hosted pages (I) |
| Incentivio | All-in-one ordering | Fast casual / franchise, digital-ordering growth (C). Poor fit | Yes. Ordering subdomain (I) |
| Olo (Wisely) (also integration) | Ordering + guest data | Enterprise / thousand-unit defaults, adopting Wisely's book (C) | Yes. Olo ordering links, Wisely waitlist widgets (I) |
| Marqii, Malou | Listings / local SEO | Discovery problem, 3+ location groups (C). Fit: "found but not returning" | Weak. Schema pages possibly (I) |
| Owner.com | Website + ordering | Independents wanting a storefront and commission-free ordering (C). Pair with Loyalist "behind the tables" | **Yes, strong.** Owner.com-built sites have recognizable footers and ordering domains (I) |
| Akia | Hotel messaging | Hotels/vacation rentals (C) | Partly. Text-us widgets (I) |
| Ovation | SMS feedback | Franchise / multi-unit (C) | Weak (I) |
| (blog) Bloom, ActiveCampaign, Brevo, SevenRooms marketing, Birdeye, Reputation, ReviewTrackers, Momos, Tattle, Podium; events: Tripleseat, SevenRooms, Perfect Venue, Releventful, Planning Pod, Hermetic AI | various | Positioned as complements or point tools (C) | Several detectable via widgets (I) |

Core positioning (C, txt/compare): "Every product here owns one slice of the guest … Loyalist is the layer underneath all of them." Sweet spot is full-service, reservation-led groups of 1–50 rooms. QSR and points-led brands are explicitly ceded (blog/guest-crm-vs-loyalty-program; Punchh compare).
**Best-fit buyer (I):** a venue site shows a Resy/OpenTable/SevenRooms/Tock widget, a Toast/Square online-ordering link, a private-dining inquiry form, and a Mailchimp signup. That is the "stack with no glue" profile.

## 4. Integrations (42 listed on integrations page; ai-instructions says 32) and web-detectability

| Category | Integrations | Detectable from public site? |
|---|---|---|
| Reservations (5) | Resy, OpenTable, SevenRooms, Tock, Wisely | **Yes, high.** Widgets and links (widgets.resy.com, opentable.com/restref, sevenrooms.com/reservations, exploretock.com) (I). OpenTable integration requires "an OpenTable Pro plan" (C) |
| POS (17) | Toast, Square, Upserve, SpotOn, Salido, Lightspeed, Omnivore, Silverware, Oracle Simphony, TouchBistro, Revel, Sauce (delivery), Parrot (LatAm), Aloha, Agilysys, Heartland, Figure | **Partly.** Online-ordering and gift-card links (order.toasttab.com, square.site, spoton, upserve) are visible. Enterprise POS (Simphony, Aloha, Agilysys) generally not (I) |
| Events / catering (3) | Tripleseat, Perfect Venue, Spoonfed | **Yes.** Tripleseat lead-form embeds, Perfect Venue inquiry links, Spoonfed catering ordering (I) |
| Hotel PMS (5) | Stayntouch, Cloudbeds, Mews, Oracle OPERA, Infor | **Partly.** Booking-engine domains (Cloudbeds, Mews) are visible. OPERA is behind SynXis-type engines (I) |
| Reviews / listings (6) | Google Reviews, Yelp, TripAdvisor, Meta (hours push), Up 'n Go, Sunday (pay-at-table) | Google/Yelp are public APIs. Sunday and Up 'n Go QR pay show up in reviews and photos (I) |
| Membership / loyalty (2) | PeopleVine (clubs), Paytronix | PeopleVine member portals are detectable (I) |
| Payments (1) | Stripe | Weak (I) |
| Ecommerce (1) | Shopify | Yes. Shop subdomain, cdn.shopify (I) |
| Ticketing (1) | DICE | Yes. dice.fm event links (music venues) (I) |
| Analytics (1) | Avero (bridges Aloha/NCR/Micros) | No (I) |

Write-back is narrower than read: tags and notes go to Resy, OpenTable and SevenRooms. POS and PMS data are read-only triggers (C, blog/the-loyalist-manifesto, blog/introducing-journeys). Partner status: Toast Partner Ecosystem since Dec 2025 (C), OpenTable integration partner (C), Resy OS partner offer (C).

## 5. Segments beyond restaurants

- Home FAQ: "restaurants, hotels, and members clubs, and anywhere else a guest is worth recognising: **museums, golf courses, concert venues, airport lounges, and cocktail bars**" (C, txt/home). Also "retail stores" (C).
- **Hotels**, real customer: The Hotel Chelsea logo (C, about/home). There are five PMS integrations and a Journeys spa/PMS example (C). Akia compare is aimed at hotel buyers (C).
- **Members clubs**: PeopleVine integration, "Clubs anchor on the member record" (blog/how-do-you-track…) (C). ZZ's Club is an MFG brand (C, PR Newswire). Jobs say "expanding into members clubs, hotels, and more" (C, Ashby). Named club customers beyond ZZ's: none found (C).
- **Music / concert venues**: DICE integration ("market by artist") (C). No named customer (C).
- **Latin America**: Parrot "for our Latin American restaurants" (C). Customer count unknown.
- **Mixed portfolios**: the "Dana" hotel + restaurant + club example (C, illustrative).
- Footprint: "1000+ venues across 40+ cities" (careers page) and "1,000+ venues across 180+ cities" (GTM Eng job) (C, inconsistent). Earlier: "hundreds of restaurants … over $2 billion in guest spend, revenue growing more than 10x" (PR, Oct 2025) (C).
- Roadmap verticals: "hotels, retail, real estate, wellness" (PR) and "residential, retail, and wellness" (manifesto) (C).
- Museums, golf and airport lounges: claim only, no named customer found (C). Treat as aspirational (I).

## 6. Product-led and inbound hooks

| Hook | Facts | GTM implication (I) |
|---|---|---|
| **Industry Insider Alert Agent** (launched 2026-11-10) | Free and "will never become a paid product". Connect Resy or OpenTable, get an 8 AM email flagging 10,000+ journalists, Michelin/Beard voters, influencers and chefs on the book. First email looks back 3 months. "1 minute to set up" (C, blog/industry-insider-alerts, /industry-insider-alerts/) | A credential-connected lead magnet. Loyalist gets the venue's reservation-platform connection and contact before any sale, which seeds an upsell base. Competing signal: any restaurant using it is pre-qualified |
| **AI Receipt Agent** (/receipts/) | Free. Auto-matches 40–70% of receipt requests on date, name and last-4. "Needs your POS and your reservations connected to Loyalist. Our team sets up the form" (C) | It requires POS and reservation integration, so it is effectively a free onboarding wedge. Stated value is 104–182 hours/year |
| **Resy partner referral** | "10% off your first year as a Resy restaurant". Offer expires Aug 31 2027. "Exclusive Loyalist partner offer" for Resy OS venues (C) | Resy venues are the priority segment, and Resy is likely a referral channel |
| **OpenTable partner referral** | "An exclusive offer for OpenTable restaurants" (no % stated) (C) | Same, via OpenTable |
| **Tripleseat events suite** (tripleseat.loyalist.com) | Inquiry form, Tripleseat-to-Resy sync, deposit links, Event VIP tag, AI events agent (C) | Co-marketing with Tripleseat. Tripleseat + Resy venues are the sharpest ICP |
| **AEO / LLM-optimized content** | /ai-instructions/ page "for AI systems"; "Talk to AI" prompt links (ChatGPT, Claude, Perplexity, Grok); demo form option "ChatGPT / Claude / AI" (C) | Heavy investment in being recommended by AI, so many leads arrive inbound via LLM answers |
| **ABM pages** | robots.txt: "/for/ … one-off links for a named account" (C, not fetched) | Account-based outbound is already in use |
| **Demo form** | Qualifies by location count (1–2, 3–10, 11–24, 25+) and "How did you hear" (C) | Location count is the primary segmentation |

## 7. Pricing, onboarding, sales motion

- No public pricing. /pricing/ shows "Loyalist Pricing Package" plus a demo CTA (C). Tiers are named **Core** and **Pro**: the Tripleseat-to-Resy sync is "included on Pro … add-on on Core" (C).
- Discounts: 10% off year one for Resy restaurants (C).
- Onboarding is white-glove: "Our onboarding team connects your systems … no engineering project on your side" (every compare page, C). History is onboarded "in about 48 hours once access is granted" (C). Data loads back to the venue's first booking (C). Tripleseat sync setup is "one session" (C). Customers should "Expect a cleanup month first" and see a first lapsed-regulars list within a month (C).
- Land-and-expand: run alongside incumbents "for a season" (C). Glendale expanded from 2 to 3 venues in two weeks (C). The Forward Deployed Strategist owns "expansion opportunities" for "enterprise restaurant groups" (C).
- Sales motion: "High-touch, in-person selling (walk-ins, network, conferences, industry relationships)"; "Multi-threaded deals across operators, GMs, and ownership groups"; "Short to medium sales cycles"; "We don't hide behind email sequences" (C, Founding AE). AE base is $70–115K with OTE $140–280K (C). The first marketing hire is open (C). Head of Growth is Julie Chen (C). The GTM Engineer will now add programmatic cold email (C).
- Proof metrics (C, blogs, Nov 2026): $56.9M attributed revenue since Nov 2023; 250k+ bookings; $14.4M from automated sequences since Mar 2026; $2M from win-backs; win-back returns 10–30% (15% average); 15% book within 30 days (Eater); 3M+ reviews.
- Trust: SOC 2 and GDPR badges on the home page (C). Seed round was $10M (Oct 2025), led by Lerer Hippeau with Bling, Floodgate, MFG and VCR Group (C).
- Typical buyer roles: owner, Director of Ops, CMO, GM, Director of Events, and the person who "owns marketing or guest relations" (C, jobs and compare).

## 8. Customer names not on the provided list

| Name | Source | |
|---|---|---|
| Carbone (MFG brand; separate logo) | /industry-insider-alerts/ logo strip; GTM Eng job "from Carbone to 4 Charles…" | C |
| Torrisi Bar & Restaurant, Sadelle's, ZZ's Club (MFG brands) | PR Newswire (Mario Carbone quote) | C (as MFG) |
| The Dinex Group (Daniel Boulud's company) | PR Newswire; Tripleseat page logo "Dinex" | C |
| Thomas Keller Restaurant Group (full name of TKRG) | /receipts/ and home logos | C |
| Tao Group Hospitality (full name of Tao) | logos | C |
| **Jeju Noodle Bar** | Founding AE job: "neighborhood spots like Jeju Noodle Bar" | C |
| **4 Charles** (4 Charles Prime Rib, NYC) | Founding GTM Engineer job | C |
| **Hawthorne & Wood** | Label above the Glendale quote on txt/demo | C (name shown). I: it may be a Glendale venue rather than a separate customer |
| **VCR Group** (Gary Vaynerchuk / David Rodolitz hospitality group) | Strategic investor (PR) | I (likely customer, not confirmed) |
| Eleven Madison Park (= EMP) | logos; ai-instructions | C (already listed) |
| Not customers (do not use): Sunn's, N/naka, Pijja Palace, Tanta, Lucia (Lucia uses SevenRooms automation) | Eater article examples | C |
| Not customers: Boka Restaurant Group (OpenTable example), Bouchon Santa Barbara (pricing source) | blogs | C |

Contacts named (C): Kyra Burner (MFG), Cedric Nicaise (The Noortwyck), Elizabeth Sharp (Glendale), Ellen Yin (High Street), Gabriel Stulman (Happy Cooking), Ellie Jackson (Grassfed), Mario Carbone (MFG), David Rodolitz (VCR). Internal (C): Maggie Tang (Founder/CEO, ex-EMP per Eater), Julie Chen (Head of Growth), "Albert" (robots.txt ABM comment).

## 9. Substack (eatloyalist.substack.com)
There are 10 posts: six mirror the blog, and four from 2023 are manifesto-style essays on "welcome back" recognition, AI copilots and comps vs punch cards. No customer profiles (C). Use them for messaging angles only (I).
