# Loyalist NYC customer dossiers: working backwards from the purchase

Research date: 2026-11-16. **C** = confirmed at the URL given. **I** = inference. "Anchor" = the earliest public date tied to Loyalist that I could find. Every anchor is an *upper bound*: the customer started on or before that date.

## How the dates were found (the methods themselves are useful signals)

- **Vendor press:** the Magic $10M seed release, 2025-10-20, names MFG, Momofuku, Le Bernardin, COTE and Dinex as users (C, https://www.prnewswire.com/news-releases/magic-raises-10m-to-bring-ai-into-the-real-world-302589060.html). Fortune adds Cosme (C, https://fortune.com/2025/10/20/mario-carbone-magic-loyalist-major-food-group-ai-restaurants-dining-crm/).
- **Partner press:** the Resy x Loyalist integration release, 2025-10-29, quotes Rezdôra/Massara (C, https://stocks.observer-reporter.com/observerreporter/article/bizwire-2025-10-29-resy-launches-new-integrations-connecting-the-resy-guestbook-to-marketing-platforms).
- **Webflow asset timestamps:** the old eatloyalist.com image IDs are MongoDB ObjectIds, whose first 8 hex characters are a Unix timestamp. The testimonial photos `6724b3c0…_photography_estela_1.avif` and `6725db62…_photography_torrisi.avif` decode to **2024-11-01** and **2024-11-02**. A Noortwyck photo also decodes to **2024-11-02** (C: asset paths on https://www.loyalist.com/ and https://www.eatloyalist.com/customer-stories/; decoded by me). The upload date is a reasonable lower bound for "already a customer with a quote" (I).
- **Notion careers page block timestamps:** the "Partners include…" text was created 2025-03-20 and last edited 2026-09 (C, loyalisttech.notion.site API). An older indexed version read "EMP, Carbone, Torrisi, The Corner Store, and Momofuku love Loyalist" (C, search snippet of https://loyalisttech.notion.site/Loyalist-Careers-1bcd38124fc480c6b94bea70f5b43424). That version probably dates from Mar–Oct 2025 (I).
- **Website footprint (technographic):** two kinds of code on customer sites mark a Loyalist customer.
  - Schema.org `ReserveAction` entries with `"propertyID":"loyalist-venue-id"` and links to `agent.eatloyalist.com/llms/<venue>.txt`.
  - The signup script `api.eatloyalist.com/signup/form/…`.
  - Found on hogsalt.com, auchevaldiner.com, nycmonkeybar.com and oriananewyork.com (C, curl 2026-11-16).
- **Not dated:** LinkedIn (not scraped) and web.archive.org (blocked). The logo wall and testimonials on loyalist.com carry no dates.

Loyalist itself: Substack started 2023-01-26 (C, https://eatloyalist.substack.com/archive). The manifesto came out 2025-04-23. The Toast partnership was announced 2025-12-16 (C, https://www.eatloyalist.com/blog/loyalist-announces-a-new-integration/). The founder worked at Eleven Madison Park (EMP), and the founding team came from USHG/EMP/Blue Hill/Atelier Crenn/MFG/The Corner Store (C, Fortune; Notion).

---

## 1. Major Food Group (MFG)
- **Structure:** founded by Carbone, Torrisi and Zalaznick (2011, I). The group now runs "more than forty restaurants, private clubs, bars, and hotels" across NYC, Miami, Las Vegas, Dallas, Paris, Hong Kong, Riyadh, London and other cities (C, https://www.majorfood.com).
- **Anchor:** **≤2024-11-02**, from the Torrisi testimonial photo timestamp (C/I, method above). Kyra Burner gives a quote about tracking guests "across all our properties" (C, https://www.eatloyalist.com/customer-stories/). MFG became an **investor** on 2025-10-20 (C, PRN).
- **Prior 12 months:**
  - ZZ's Club NYC members club opened, report dated 2023-11-20 (C, https://hospitalitydesign.com/news/f-b/zzs-club-new-york/).
  - Carbone Riyadh opened Nov 2023 (C, search summary of https://www.verdictfoodservice.com/news/carbone-london-uk).
  - Chateau ZZ's Miami club, Jan 2024 (C, https://www.modernluxury.com/major-food-grou-chateau-zz-brunch/).
  - Carbone Dubai announced 2024-05-29 (C, https://hospitalitydesign.com/news/carbone-dubai-atlantis-the-royal/164288).
  - Carbone Hong Kong was in development in 2024 (C, same search).
- **After the anchor:** Carbone London opened Sep 2025. Major's Grill (London) was announced 2025-10-16 for Q2 2026 (C, https://www.restaurantonline.co.uk/Article/2025/10/16/carbone-operator-major-food-group-to-bring-major-grill-to-mayfairs-cambridge-house-auberge-collection-hotel).
- **Reservations:** Resy (majorfood.com, carbonenewyork.com and torrisinyc.com all link to resy.com; torrisinyc.com also uses Tripleseat) (C, curl).
- **Decision-makers:** co-founders Mario Carbone, Rich Torrisi and Jeff Zalaznick. Kyra Burner is the quoted user (role not public).

## 2. Happy Cooking Hospitality (Gabriel Stulman)
- **Structure:** founded 2009 (Joseph Leonard), West Village. Four venues are listed now: Joseph Leonard, Jeffrey's Grocery, Fairfax and Sailor (Fort Greene) (C, https://www.happycookingnyc.com/). Sailor opened Sep 2023 (C, https://en.wikipedia.org/wiki/Gabriel_Stulman). Jolene no longer appears on the homepage, so it probably closed (I).
- **Anchor:** **undated.** Stulman's quote calls himself "a proud early adopter" (C, customer-stories). "Early adopter" points to 2023–24 (I).
- **Prior 12 months:** Sailor opened Sep 2023 with April Bloomfield (C, Wikipedia). If adoption was in 2023–24, a new borough or venue is the likely trigger (I).
- **Reservations:** OpenTable (BentoBox `data-reservation-service="opentable"`) (C, curl).
- **Decision-maker:** Gabriel Stulman (founder). Gina Stulman (partner/design) (C, our-story page).

## 3. The Noortwyck + Oriana (Cedric Nicaise, Andrew Quinn)
- **Structure:** The Noortwyck (289 Bleecker; announced 2021-12-17, opened 2022-06-07) (C, https://whatnowny.com/nyc-wine-expert-plots-elevated-new-restaurant/; https://www.timeout.com/newyork/news/the-noortwyck-is-a-new-seasonal-american-restaurant-from-fine-dining-alums-060622). Oriana (174 Mott, Nolita) opened **2026-05-28** (C, https://blog.resy.com/2026/05/oriana-nyc/; https://galavante.com/destinations/new-york-city/oriana-nyc-the-noortwyks-next-move/). Both founders are EMP alumni; Nicaise was EMP's director of operations (C).
- **Anchor:** **≤2024-11-02** (testimonial photo timestamp, C/I). Eater, 2026-08-05: Nicaise "has employed" Loyalist for targeted follow-up (C, https://www.eater.com/dining-out/978611/restaurants-sending-emails-post-meal-follow-ups). Oriana's site embeds the Loyalist signup form (C, curl of https://www.oriananewyork.com), so Loyalist was installed at the **new venue at launch**.
- **Prior 12 months (Nov 2023–Nov 2024):** I found no opening or award. Nicaise was on the Salon Nov 2024 press circuit (C, https://www.salon.com/2024/11/13/quality-prevails-chef-andy-quinn-on-why-new-york-city-offers-more-holistic-dining-than-the-uk). The strongest driver is the **EMP alumni tie to Loyalist's founder** (I).
- **Reservations:** both venues are on Resy (Noortwyck `data-reservation-service="resy"`; Oriana resy.com/…/oriana). POS is Toast (gift cards) (C, curl).
- **Decision-makers:** Cedric Nicaise (co-owner, wine/ops) and Andrew Quinn (chef/co-owner).

## 4. Eleven Madison Park (Make It Nice)
- **Structure:** a single flagship with three Michelin stars. Chef-owner Daniel Humm (Make It Nice).
- **Anchor:** **undated, probably by mid-2025 (I).** EMP is named on the older careers-page version and in the homepage FAQ (C, https://www.eatloyalist.com/). The founder briefly worked in EMP dining-room operations (C, Fortune).
- **Prior/around events:**
  - Announced Aug 2025 that meat and seafood return from Oct 2025, ending four years of a plant-based menu (C, https://www.cbsnews.com/amp/newyork/news/eleven-madison-park-ends-vegan-only-menu).
  - Humm said **private-dining/event, corporate and group bookings and wine sales** had fallen (C, https://www.finedininglovers.com/explore/articles/daniel-humm-eleven-madison-park-meat-returns).
  - That is a revenue-recovery and win-back motive (I).
- **Reservations:** Resy (C, curl).
- **Decision-maker:** Daniel Humm (chef/owner).

## 5. Le Bernardin
- **Structure:** NYC since 1986. Aldo Sohm Wine Bar opened 2014 (C, search summary). Three Michelin stars every year since 2005 (C, https://www.opentable.com/r/le-bernardin).
- **Anchor:** **≤2025-10-20** (C, PRN; Fortune). Logo is on the customer-stories page.
- **Prior 12 months:** no new venue. It made the World's 50 Best extended list (51–100), Jun 2025 (C, https://www.timeout.com/newyork/news/two-nyc-restaurants-just-cracked-the-worlds-100-best-restaurants-list-for-2025-060525). After the anchor it was named La Liste's best in the world for 2026 (C, https://secretnyc.co/de/la-liste-le-bernardin-beste-der-welt-2026/). No change detected, so this was a **steady-state "retain regulars" buy** (I).
- **Reservations:** Resy (widgets.resy.com) (C, curl).
- **Decision-makers:** Eric Ripert (chef/co-owner) and Maguy Le Coze (co-owner).

## 6. COTE (Gracious Hospitality Management, Simon Kim)
- **Structure:** COTE NYC (2017), Miami, Singapore and Las Vegas, plus COQODAQ (2024) and the 550 Madison complex (COTE 550 and Bar Chimera, around Apr 2026) (C, https://hospitalitydesign.com/news/cote-korean-steakhouse-venetian-las-vegas/184721; resy.com/2026/04/cote-550-bar-chimera link on cotekoreansteakhouse.com).
- **Anchor:** **≤2025-10-20** (C, PRN). The Notion partner list also names COTE.
- **Prior 12 months:**
  - **COTE Las Vegas opened 2025-10-06** at the Venetian, a 17,000 sq ft fourth global location (C, https://www.venetianlasvegas.com/media/news-releases/2025/10-06-cote-korean-steakhouse-arrives-in-las-vegas.html). That is two weeks before the anchor.
  - 550 Madison, the "largest project to date," was pushed from 2H25 to 2026 (C, https://hospitalitydesign.com/news/simon-kim-new-york-restaurants/160719).
- **Reservations:** **mixed.** NYC and Miami use Resy; Las Vegas and Singapore use SevenRooms. Tripleseat handles events (C, curl). A CRM that sits across several booking systems fits this setup (I).
- **Decision-maker:** Simon Kim (founder/CEO).

## 7. Daniel Boulud (Dinex Group)
- **Structure:** Daniel, Café Boulud (reopened Dec 2023 at 100 E 63rd), Maison Barnes, Le Pavillon, Jōji, Le Gratin (2022), **La Tête d'Or (opened Nov 2024)** and Brasserie Boulud (Oct 2026), plus international venues (C, https://www.businesswire.com/news/home/20241114292410/en/Chef-Daniel-Boulud-Opens-La-Tte-dOr; https://nyrej.com/print/51323; https://www.morningstar.com/news/business-wire/20261008950797/chef-daniel-boulud-opens-brasserie-boulud).
- **Anchor:** **≤2025-10-20** (C, PRN).
- **Usage evidence:**
  - A Loyalist x Dinex events-CRM workshop was co-hosted by Marisa Colangelo, Dinex Corporate Director of Sales, on 2026-04-27 (C, https://luma.com/vphsjfzs).
  - The deck shows a campaign to "closed or lost events in Q3 2025" sent by a **new Senior Events Manager** at Café Boulud/Maison Barnes, with Tripleseat-synced holds (C, https://docs.google.com/presentation/d/1UN955oiz0PWJTjfYVrUf3UHsUCAFDjwT/htmlpresent).
- **Prior 12 months:** La Tête d'Or opened Nov 2024 (C). Maison Barnes event space was added in 2024 (C, NYREJ). A new events hire arrived around Q3–Q4 2025 (C/I).
- **Reservations:** Resy (danielnyc.com, cafeboulud.com/nyc) (C, curl).
- **Decision-makers:** Daniel Boulud. Sebastien Silvestri (CEO) (C, BW). Marisa Colangelo (Corporate Director of Sales).

## 8. Momofuku
- **Structure:** founded 2004 by David Chang. It has shrunk to a few venues (NYC Noodle Bar and Bar Kabawa, Las Vegas, LA Super Peach) and shifted toward packaged goods (C, https://www.restaurantbusinessonline.com/leadership/momofuku-names-its-1st-ceo).
  - Closures: Ssäm Bar 2023-09-30 (C, https://www.timeout.com/newyork/news/momofuku-ssaem-bar-by-david-chang-is-closing-at-the-end-of-the-month-091123); Ko Nov 2023; Toronto Dec 2025; Bang Bar LV 2026-10-04.
- **Anchor:** **≤2025-10-20** (C, PRN; Fortune). It is also on the older careers-page version (probably by mid-2025, I).
- **Prior 12 months:**
  - **Bar Kabawa opened Feb 2025** in the East Village with Paul Carmichael (C, https://plateonline.com/node/1401922).
  - Super Peach Century City was planned for spring 2025 (C, https://whatnowlosangeles.com/momofuku-opening-new-concept-in-westfield-century-city).
  - Pattern: portfolio consolidation, so getting more from the remaining regulars matters (I).
- **Reservations:** **OpenTable**, including Experiences links (C, curl of momofuku.com).
- **Decision-makers:** David Chang (founder) and Marguerite Mariscal (CEO).

## 9. Estela (Mattos Hospitality, Ignacio Mattos)
- **Structure:** Estela (2013), Altro Paradiso, Lodi (Rockefeller Center, 2021), and Corner Bar and Amado at Nine Orchard (C, https://blog.resy.com/2021/09/six-things-you-need-to-know-about-new-yorks-lodi/; https://whatnowny.com/michelin-starred-chef-ignacio-mattos-to-debut-whimsical-and-romantic-restaurant-this-year/).
- **Anchor:** **≤2024-11-01** (Estela testimonial photo timestamp; C/I). The quote praises the "centralized VIP line and guest look-up" for "our guest relations" (C, customer-stories). The Estela logo appears on Loyalist's OpenTable partner page (C, https://www.loyalist.com/opentable-partner-referral/).
- **Prior 12 months:** the multi-venue Nine Orchard openings (2022–23) and a centralized guest-relations function (I; exact dates not confirmed).
- **Reservations:** OpenTable, with Toast POS (C, curl of estelanyc.com).
- **Decision-maker:** Ignacio Mattos (chef/owner).

## 10. Cosme (Enrique Olvera)
- **Structure:** Cosme NYC (2014). Atla NYC closed May 2026, and Bar Cosme took its space in Nov 2026 (C, https://www.timeout.com/newyork/news/cosme-is-opening-a-brand-new-bar-in-noho-this-fall-071126). The group also runs LA venues (Damian, Ditroit) and Mexico City.
- **Anchor:** **≤2025-10-20** (C, Fortune). Logo is on the customer-stories page.
- **Prior 12 months:** no dated NYC event found. After the anchor came a closure and replacement (Atla → Bar Cosme), which suggests Loyalist data feeds relaunch marketing (I).
- **Reservations:** Resy (C, curl).
- **Decision-maker:** Enrique Olvera (chef/owner).

## 11. Union Square Hospitality Group (USHG)
- **Structure:** founded 1985 by Danny Meyer, NYC-based. It runs Gramercy Tavern, Union Square Cafe and others.
  - Expansion: Boston Seaport (2025) (C, https://totalfood.com/union-square-hospitality-group-hub-expansion-in-2025/); The View, Times Square (2025) (C, https://thecarboholic.substack.com/p/nyc-2025-restaurant-openings-a-running); Detroit (2026); Brooklyn (2028) (C, https://www.timeout.com/newyork/news/danny-meyers-award-winning-union-square-hospitality-group-is-opening-its-first-ever-full-service-restaurant-in-brooklyn-in-2028-052726).
- **Anchor:** **undated.** Logo is on the loyalist.com homepage and the Resy partner page (C). Loyalist's founding team includes USHG alumni (C). USHG also has a long-running Thanx partnership (C, https://www.fsrmagazine.com/content/union-square-hospitality-group-forms-growing-partnership-thanx), so Loyalist may be an add-on or replacement (I).
- **Prior events:** out-of-market expansion (Boston, Detroit) and an iconic-venue takeover (The View) (C), dates relative to purchase unknown.
- **Reservations:** OpenTable (gramercytavern.com/reservations, unionsquarecafe.com) (C, curl).
- **Decision-maker:** Danny Meyer (founder).

## 12. Hotel Chelsea
- **Structure:** reopened 2022 after an 11-year closure. Owners: Sean MacPherson, Ira Drukier and Richard Born (C, https://hospitalitydesign.com/people/interviews/ira-drukier-sean-macpherson-richard-born/). Outlets: Café Chelsea, El Quijote, and **Teruko** (basement Japanese restaurant, around Jun 2025) (C, https://hotelsabovepar.com/travel-guides/hotel-chelsea-teruko-japanese-restaurant-nyc). Michelin Key 2024 (C, search).
- **Anchor:** **undated.** Logo is on the homepage and the Resy partner page (C).
- **Prior events (possible):** Teruko launch (Jun 2025). The owners also pursued the Washington Square Hotel through a liquor-license transfer (Aug 2025) (C, https://www.readfeedme.com/p/sean-macpherson-bought-another-hotel). This is a hotel plus several F&B outlets, the kind of setup that needs one guest profile (I).
- **Reservations:** Resy (C, curl).
- **Decision-makers:** Sean MacPherson, Ira Drukier and Richard Born (owners).

## 13. Atomix (NA:EUN Hospitality)
- **Structure:** Atomix (2018), Atoboy and Naro. Two Michelin stars.
- **Anchor:** **none found.** It is not on Loyalist's pages, and no press ties it to Loyalist. It is a customer only per the brief.
- **Events, 2025:**
  - No. 12 on World's 50 Best (Jun 2025).
  - **No. 1 on the inaugural North America's 50 Best** (2025-09-26) (C, https://kyodonewsprwire.jp/release/202509266002).
  - James Beard Outstanding Hospitality award (C, search summary).
- **Reservations:** Tock (C, curl). Tock is a prepaid ticketing system, so its guest data lives apart from other systems (I).
- **Decision-makers:** Junghyun "JP" Park and Ellia Park.

## 14. Rezdôra (and Massara; Stefano Secchi)
- **Structure:** Rezdôra (2019) and **Massara (opened Jun 2024)**, about a minute's walk apart (C, https://www.finedininglovers.com/index%2ephp/experts/stefano-secchi).
- **Anchor:** **≤2025-10-29.** Lucy Barrow, head of business and operations, is quoted as a "Loyalist user" in the Resy integration release (C, BW link above).
- **Prior 12–16 months:** the second venue opened (Jun 2024), and a **business/ops lead** role appears in the quote (C).
- **Reservations, now:** **SevenRooms on both** sites (rezdora.nyc BentoBox `data-reservation-service="sevenrooms"`; massara.nyc links to sevenrooms) (C, curl). In Oct 2025 they spoke as Resy users, so they **moved from Resy to SevenRooms after the anchor** (I, strong). Loyalist kept the account across the reservation-platform change (I).
- **Decision-makers:** Stefano Secchi (chef/owner) and Lucy Barrow (head of business and operations).

## 15. Jeju Noodle Bar (Douglas Kim)
- **Structure:** one venue in the West Village (2017). Michelin star since the 2019 guide (C, https://guide.michelin.com/us/en/article/dining-out/jeju-noodle-bar-douglas-kim-video). **Second location at 204 Elizabeth St, Nolita**, reported 2025-09-24, targeting spring 2026 (C, https://whatnow.com/?p=334097).
- **Anchor:** **none found.**
- **Events:** No. 16 on the NYT 100 Best list, 2024 (C, search summary). A second unit was being built through 2025–26 (C).
- **Reservations:** Resy (C, curl).
- **Decision-maker:** Douglas Kim.

## 16. Hogsalt (4 Charles Prime Rib, Au Cheval NYC)
- **Structure:** Chicago-based, founded by Brendan Sodikoff. Venues in Chicago, New York (4 Charles, Au Cheval at 33 Cortlandt Alley, Monkey Bar at 60 E 54th), Nashville, Las Vegas and Paris (La Renommée) (C, JSON-LD on hogsalt.com; https://pariscapitale.com/en/restaurants-paris-en/traditional/la-renommee/).
- **Anchor:** **undated, but there is a live footprint.** hogsalt.com, auchevaldiner.com and nycmonkeybar.com list about 10 venues (including 4 Charles and Au Cheval New York) as bookable "via the Loyalist agent booking network," each with a `loyalist-venue-id` (C, curl).
- **Prior events:** Monkey Bar revived by Hogsalt around 2023 (C, https://galavante.com/destinations/new-york-city/monkey-bar/; date I). Paris expansion. Opening dates relative to purchase are unknown.
- **Reservations:** Resy (widgets.resy.com on nycprimerib.com and Au Cheval). Tripleseat handles events (C, curl).
- **Decision-maker:** Brendan Sodikoff (founder).

---

## Cross-customer patterns

**Anchors cluster in two windows.** The **Nov 2024** window (asset timestamps) covers MFG, Noortwyck and Estela. The **Oct 2025** window (seed and Resy press) covers Le Bernardin, COTE, Dinex, Momofuku, Cosme and Rezdôra. That gives 9 of 16 with a datable upper bound; 7 of 16 have no date (Happy Cooking, EMP, USHG, Hotel Chelsea, Atomix, Jeju, Hogsalt). The Oct 2025 cluster reflects when Loyalist *announced*, not when each customer *bought*. Real purchase dates are earlier, probably by 3–12 months (I).

| Pre-purchase event | k / n (among 9 datable) | Lag before anchor | Publicly detectable? |
|---|---|---|---|
| New venue opened or announced, or a second unit | **5/9**: MFG (clubs/intl), COTE (LV), Dinex (La Tête d'Or), Momofuku (Bar Kabawa), Rezdôra (Massara). Among undated: Jeju, Noortwyck→Oriana and USHG also fit, so 8/16 overall | 2 wks–16 mo; median about 8–11 mo (I, upper-bound lags) | Yes: press, Resy/Eater, NY SLA liquor-license filings (not pulled here) |
| Multi-venue or cross-property guest view is the stated need | 5/9 (MFG "across all our properties", COTE, Dinex, Rezdôra, Mattos "centralized guest relations") | n/a | Yes: venue count on group site; mixed reservation systems |
| Private events or event sales push | 3/9 dated (Dinex events hire and Tripleseat, MFG members clubs, COTE Tripleseat). Plus EMP citing fallen private-dining revenue | 0–6 mo | Partly: Tripleseat links on site, events-manager job posts |
| Founder or alumni network tie (EMP/USHG/MFG/Corner Store) | 4/16 (EMP, Noortwyck, USHG, MFG) | n/a | Yes: LinkedIn bios, press |
| Major award or list | 2/9 (Le Bernardin W50B extended; Atomix NA50 #1 is undated) | ~4 mo | Yes, but **weak** signal; elite venues buy without a fresh award |
| Reservation-platform change | 0/9 before purchase. 1 *after* (Rezdôra Resy→SevenRooms) | after | Yes (curl the widget) |
| Ops, guest-relations or events hire | 2/9 (Dinex new Senior Events Manager; Rezdôra head of business/ops) | 0–6 mo | Job boards (NYC postings now list "Loyalist preferred" (C, search: jobtoday/ziprecruiter)) |
| Funding or ownership change | 0/9 before; MFG invested *after* using it | after | n/a |

**Takeaways (I):**
1. The repeatable trigger is **going from one venue to several**: a second unit, a new city, or a hotel/club outlet. Guest data then splits across venues and systems, which is the "Fragmentation Tax" in Loyalist's own pitch.
2. **Revenue pressure on high-margin guests** (private dining, win-back) is the second driver: EMP, Dinex, Momofuku's consolidation.
3. Reservation platform is **not** a qualifier. Customers span Resy (10), OpenTable (4: Momofuku, Estela, Happy Cooking, USHG), SevenRooms (Rezdôra/Massara, COTE LV/SG) and Tock (Atomix). The Resy (Oct 2025) and Toast (Dec 2025) integrations widen reach but say nothing about intent.
4. **Best direct detector** for current customers: grep venue sites for `eatloyalist.com`, `loyalist-venue-id` or `api.eatloyalist.com/signup` (found on 4 sites across Hogsalt and Oriana). Also job posts that mention "Loyalist."
5. **Best leading indicators** for prospects: a group with 1–3 NYC fine-dining venues announcing another venue (press or SLA filing), a group mixing reservation systems across venues, and new events or guest-relations hires.
