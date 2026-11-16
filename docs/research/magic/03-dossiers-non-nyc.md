# 03 — Loyalist customer dossiers (mostly non-NYC), work-backwards

Research date: 2026-11-16. C = confirmed (URL given), I = inference. Wayback/archives were not available, so no logo or testimonial on loyalist.com could be dated directly. "Loyalist start" therefore means the **earliest public evidence I could find**, which is an upper bound on when they actually started.

**Loyalist-side sources used throughout**
- Customer-stories page with quotes from Glendale (Elizabeth Sharp), High Street (Ellen Yin), Mattos ("Team") and Grassfed (Ellie Jackson). The page carries no dates. C https://www.loyalist.com/customer-stories/
- Homepage logo strip shows STARR, Tao, Thomas Keller, USHG, Hotel Chelsea and The Noortwyck. C https://www.loyalist.com/
- Careers page lists "Partners include: Carbone, Torrisi, EMP, COTE, STARR Restaurants, and TAO Group" and "15% of all Michelin-starred restaurants". Notion block metadata: created 2025-03-20, last edited 2026-09-21. The partner list could have been added at any point between those dates. C https://loyalisttech.notion.site/Magic-Careers-1bcd38124fc480c6b94bea70f5b43424
- Substack manifesto, 2025-04-23, names "Major Food Group, Mattos Hospitality, Momofuku, and Eleven Madison Park". C https://eatloyalist.substack.com/p/the-loyalist-manifesto
- Seed round of $10M (Lerer Hippeau, MFG), 2025-10-20. The press release names MFG, Momofuku, Le Bernardin, COTE and Dinex, and none of the customers in this file. C https://www.vcaonline.com/news/2025102004/magic-raises-10m-to-bring-ai-into-the-real-world/
- Toast partnership, 2025-12-16. C https://www.loyalist.com/blog/loyalist-announces-a-new-integration/
- **New dating method:** venue websites embed `api.eatloyalist.com/signup/form/<uuid>` (the Loyalist email capture form) or `agent.eatloyalist.com` (an LLM/MCP agent file). Curl detects these cheaply. It shows a venue is a current customer, but the UUIDs carry no date.

---

## 1. Glendale Hospitality (Chapel Hill, NC)
**Structure:** Owned by Chef Brandon Sharp, Elizabeth Sharp and Neal Benefield (Director of Operations and beverage). It has 3 venues, all in Chapel Hill: Hawthorne & Wood (2019), Bluebird (French bistro, Meadowmont, 2022) and Próximo (Spanish tapas, 173 E. Franklin St.). The group's website shows a "coming soon" slot in its portfolio. C https://www.glendalehospitality.com/ · C https://www.axios.com/local/raleigh/2024/03/26/michelin-star-chef-big-franklin-street-bet-proximo-brandon-sharp
**Loyalist evidence:** Elizabeth Sharp is quoted: "We are a small group of three restaurants… try Loyalist… for our two bigger, more established restaurants… within two weeks… no way we weren't going to enroll the third." (C customer-stories). All three sites embed Loyalist signup forms (C, curl of hawthorneandwood.com, bluebirdnc.com, proximonc.com).
**Dating:** The quote only makes sense once there were three restaurants, so the start is **after Próximo opened (Sept 2024)**. The "third restaurant" they enrolled later is most likely Próximo, the youngest venue (I). Window: roughly late 2024 to 2025 (I).
**12 months before:**
- 2024-03-26: Próximo announced (Axios, "Michelin-starred chef's big Franklin Street bet"). C URL above
- 2024-09 (third week): Próximo opens after a media preview, with Benefield running the beverage program. C https://www.axios.com/local/raleigh/2024/09/18/first-look-proximo-spanish-restaurant-chapel-hill-franklin-street · C https://chapelboro.com/news/business/new-spanish-tapas-restaurant-opens-after-renovation-of-familiar-east-franklin-street-space
- Elizabeth Sharp has served on Chapel Hill Town Council since 2023, so a co-owner has less time for marketing (I). C https://www.chapelhillnc.gov/Elected-officials/Elizabeth-Sharp
- 2025-09-11: Axios "Local Limelight" profile of Brandon Sharp. This is press after the start date. C https://www.axios.com/local/raleigh/2025/09/11/local-limelight-chef-brandon-sharp-of-hawthorne-wood
**Reservations (curl):** Hawthorne & Wood uses a Resy link (resy.com/cities/rdu/hawthorne-and-wood). The Bluebird and Próximo homepages showed no reservation widget (they are Wix sites, so it may be loaded by JavaScript). C
**Decision-makers:** Elizabeth Sharp (co-owner, the person quoted), Brandon Sharp (chef/owner), Neal Benefield (Director of Operations).
**Pattern:** A third venue opened. The trial started with the established venues and spread to the new one, which is land-and-expand inside one group.

## 2. High Street Hospitality Group (Ellen Yin, Philadelphia)
**Structure:** Fork (1997), High Street (101 S. 9th St., with The Back Room private-dining space; Executive Chef Christina McKeough), a.kitchen+bar at AKA Rittenhouse, a.kitchen+bar DC (at Hotel AKA Washington Circle), and The Bread Room (bakery, workshop and event space). C https://highstreetonmarket.com/ (highstreetphilly.com redirects there)
**Loyalist evidence:** Ellen Yin is quoted: Loyalist helped "segment our guests… especially valuable for private events… as we head into the holiday season!" (C customer-stories). The Fork and High Street sites embed `agent.eatloyalist.com` LLM/MCP files and the Loyalist API (C, curl).
**Dating:** The quote was written in some autumn. The likely candidates are fall 2024 (after the DC opening) or fall 2025 (after The Bread Room event space opened) (I). **I could not date it exactly.**
**12 months before (both candidates):**
- 2024-05-01: Hotel AKA Washington Circle opens. This is their third AKA partnership. C https://www.hospitalitynet.org/announcement/41010985.html
- 2024-09-19: a.kitchen+bar opens in DC, the group's first venue outside Philadelphia. Washingtonian headline: "James Beard's Outstanding Restaurateur from Philly makes DC debut" (Yin won the 2023 JBF award). C https://www.washingtonian.com/2024/09/19/james-beards-outstanding-restaurateur-from-philly-makes-dc-debut
- 2025-07-09: The Bread Room announced as a "bakery, workshop, and event space". C https://inquirer.com/food/restaurants/ellen-yin-bread-room-bakery-high-street-20250709.html
- 2025-10-14: The Bread Room opens. C https://www.inquirer.com/food/restaurants/the-bread-room-high-street-ellen-yin-20251014.html
**Reservations (curl):** Fork and High Street both use OpenTable, including OpenTable "experiences" links. Both sites also run Toast. C
**Decision-makers:** Ellen Yin (founder/owner, the person quoted), Christina McKeough (Executive Chef, High Street), Eli Collins (Executive Chef, a.kitchen). C (Collins: https://philadelphia.today/2024/11/ellen-yin-a-kitchen-washington/)
**Pattern:** A hotel-partner opening in a new market, plus new private-event space. The buying need she states is private-events marketing.

## 3. Mattos Hospitality (identified: chef Ignacio Mattos, NYC)
**Identity:** This is Ignacio Mattos's group, **not** non-NYC. Its site lists Estela (2013, Michelin 1★) and Altro Paradiso. Lodi (Rockefeller Center, 2021) and Corner Bar/Swan Room (Nine Orchard hotel, 2022) are no longer listed. C https://mattoshospitality.com/ · C https://guide.michelin.com/en/new-york-state/new-york/restaurant/estela
**Loyalist evidence:** The earliest dated mention is **2025-04-23** (Substack manifesto). The "Team" quote praises the "centralized VIP line and guest look-up" (C customer-stories). Neither the Estela homepage nor the mattoshospitality.com homepage carries a Loyalist embed.
**12 months before (Apr 2024 to Apr 2025):**
- 2024-02-22: Mattos walks away from Corner Bar and Swan Room at Nine Orchard and drops the planned Amado Grill. This is a portfolio contraction just before the window. C https://www.yahoo.com/news/lifestyle/acclaimed-chef-ignacio-mattos-walking-020000817.html
- Estela kept its Michelin star in the 2025 NYC guide. C Michelin URL above
- Reservation platform change: a Tock FAQ page for Estela still exists (exploretock.com/estela/faq), but the current site says "Reservations are available via OpenTable" and loads the OpenTable widget (rid 212488). This points to a **Tock to OpenTable switch** at some point (I; date unknown). C (curl of estelanyc.com)
**Decision-makers:** Ignacio Mattos (chef/owner). Guest-relations leads are implied by the "VIP line" quote, but no name is given.
**Pattern:** Consolidating to a smaller set of venues, centralizing guest relations, and changing reservation platform.

## 4. Grassfed Culture Hospitality (Miami → Atlanta)
**Structure:** Founded in 2020 by Josh Hackler (CEO), Pili Restrepo (creative director) and Sebastián Vargas (executive chef). Miami venues: Los Félix (2021; Michelin ★ 2022–2026, Green ★ 2024–25), Krüs Kitchen (Green ★ 2024–25), ZeyZey (Little River music venue, opened 2023-07-14) and Tacos María (now ZeyZey's food concept). Atlanta venues, both in Stella at Star Metals: Füm (opened Feb 2026) and Rabbit Ears (17th-floor bar; as of May 2026 it was awaiting approvals, and it now has an OpenTable page). C https://www.grassfedculture.com/ · C https://www.ajc.com/food-and-dining/2026/02/why-a-michelin-starred-miami-restaurant-group-is-betting-on-atlanta
**Loyalist evidence:** Ellie Jackson is quoted: "I hadn't worked with a CRM like Loyalist before **joining Grassfed**." (C customer-stories). Los Félix, Krüs, Füm and Rabbit Ears all embed Loyalist signup forms (C, curl). Rabbit Ears' site is almost nothing but a Loyalist form, which is a pre-opening waitlist.
**Dating:** No date. Loyalist was clearly in place by Füm's Feb 2026 opening, because Rabbit Ears used Loyalist for pre-opening capture (I). The most likely start is mid-to-late 2025, during the Atlanta build-out (I).
**12 months before:**
- 2025-04-17: Florida Michelin ceremony; Los Félix keeps its ★ and Green ★, and Krüs keeps its Green ★. C https://guide.michelin.com/en/article/michelin-guide-ceremony/michelin-stars-florida-guide-ceremony-miami-orlando-tampa
- **2025-06-04: an Atlanta building permit application for "Füm" makes news.** This is out-of-market expansion, visible about 8 months before opening. C https://whatnow.com/atlanta/restaurants/miami-based-group-bringing-new-restaurant-to-west-midtown/
- 2025-09-25: ZeyZey relaunches as a full-time indie music venue with Tacos María. C https://www.timeout.com/miami/news/big-things-are-happening-at-zeyzey-miamis-new-epicenter-for-live-indie-music-in-little-river-092525
- New marketing/CRM hire: Ellie Jackson (I, from her quote; her title was not found).
- 2026-02 (mid-month): Füm opens. C https://roughdraftatlanta.com/2026/02/18/fum-italian-restaurant-opens-stell-star-metals-atlanta/
**Reservations (curl):** OpenTable at Los Félix, Krüs and Füm. Toast is on the sites. C
**Decision-makers:** Josh Hackler (CEO), Pili Restrepo, Sebastián Vargas, and Ellie Jackson (the day-to-day user).
**Pattern:** Out-of-market expansion, a new marketing hire, and continued Michelin status. This is the clearest case of the full signal stack.

## 5. STARR Restaurants (Philadelphia, NYC, DC, Miami, Nashville, Atlantic City, Paris)
**Structure:** Stephen Starr's group, about 43 restaurants. In 2025 it opened Pastis Nashville (2025-06-26), Chez Frites plus a second concept at Ocean Casino in Atlantic City (summer 2025), Borromini in Philadelphia (2025-08-25, its first new Philadelphia restaurant in 3 years) and Slim's at Bal Harbour in Miami (late 2025/2026). A Devon Seafood site in Rittenhouse is targeted for late 2026. C https://www.axios.com/local/philadelphia/2025/08/25/borromini-opens-philly-stephen-starr · C https://en.10minhotel.com/2025/06/05/starr-restaurants-to-open-parisian-bistro-pastis-in-nashville · C https://njbiz.com/stephen-starr-restaurants-atlantic-city-opening/
**Loyalist evidence:** Logo on loyalist.com, named as a partner on the careers page (between 2025-03 and 2026-09), and a Loyalist signup form on starr-restaurants.com (C, curl). **I could not date the start.**
**12 months before:** Whatever the exact date, the period from 2025 into 2026 was STARR's densest run of openings in years, across four new markets/venues (C above). That fits "openings precede purchase" (I).
**Reservations:** starr-restaurants.com shows no booking widget in its static HTML; individual venues were not checked.
**Decision-makers:** Stephen Starr (founder). Corporate marketing and guest-relations leads were not identified.

## 6. Thomas Keller Restaurant Group (Yountville, NYC, Las Vegas, Montecito)
**Structure:** The French Laundry (3★), Per Se (3★), Bouchon Bistro and Bakery (Yountville and Las Vegas), Ad Hoc, La Calenda, and Coral Casino F&B in Montecito (Ty Warner partnership announced July 2023). C https://www.fsrmagazine.com/growth/hotel-lodging/ty-warner-hotels-resorts-partners-with-thomas-keller/
**Loyalist evidence:** Only the logo on the loyalist.com homepage (C). thomaskeller.com has no Loyalist embed. **I could not date the start.**
**Recent events:** A 2024 NYT review called TFL and Per Se overpriced (C https://www.sonomamag.com/?p=126010). French Laundry garden tours were revived as a $100 Tock experience in 2026 (C https://www.pulse.bot/food/news/thomas-kellers-french-laundry-garden-tours-return-for-100-75minute-experience-d612a3a5-6739-4285-8917-ab7682209a37). There are rumors of a Dallas opening (Aug 2026, unconfirmed) (C https://www.dmagazine.com/micropost/thomas-keller-rumors-intensify/). The reputation pressure plus new paid experiences suggest a retention and repeat-guest motive (I).
**Reservations (curl):** Tock (exploretock.com/tfl, /perse, /frenchlaundryculinarygarden). C
**Decision-makers:** Thomas Keller (owner). Others not identified.

## 7. Tao Group Hospitality (NYC, LV, LA, Chicago, international)
**Structure:** Brands include Tao, Lavo, Marquee, Hakkasan and others, with 80+ venues worldwide. In **May 2023** a majority stake was sold to Mohari Hospitality ($550M valuation); co-CEOs Noah Tepperberg and Jason Strauss stayed on. C https://www.hotelmanagement-network.com/news/mohari-hospitality-acquires-tao-group-for-550m/
**Loyalist evidence:** Logo on the loyalist.com homepage, and named as a partner on the careers page (2025-03 to 2026-09 window). taogroup.com has no Loyalist embed. **I could not date the start.**
**12 months before:** Not determinable. The ownership change (2023) is the main structural event; Tao-branded hotel plans were reported but not confirmed (I).
**Reservations (curl):** taogroup.com mixes OpenTable (several rids) and Tock (exploretock.com/lavo), and also runs Mailchimp. C
**Decision-makers:** Tepperberg and Strauss (co-CEOs); Justin Levy (Senior Director, Digital Marketing), who is quoted in OpenTable's marketing.

## 8. Rose's Luxury (Aaron Silverman, Washington DC)
**Structure:** Rose's Restaurant Group: Rose's Luxury (2013, Michelin ★), Pineapple & Pearls, Little Pearl and a catering company. C https://blog.resy.com/2026/01/roses-luxury-washington-dc/
**Loyalist evidence:** **None found.** There is no Loyalist embed on rosesluxury.com or pineappleandpearls.com; both use BentoBox email signup. **I could not date the start.**
**Possible pre-purchase events:** The group filed an SEC Form D for $250k of debt (first sale 2026-08-28, filed 2026-09-21), so new capital came in (C https://vcbeast.com/deals/roses-management-group-form-d-2026-08-28). Pineapple & Pearls' booking page is titled "reservations-coming-soon" but currently links to Resy, so it may have reopened or relaunched (I). Resy ran a group feature in Jan 2026 (C).
**Reservations (curl):** Resy at Rose's Luxury (including a Rooftop Garden listing) and at Pineapple & Pearls. C
**Decision-makers:** Aaron Silverman (chef/owner, listed as executive officer on the Form D).

## 9. Mozza (Nancy Silverton, Los Angeles)
**Structure:** Osteria Mozza, Pizzeria Mozza, Chi Spacca, plus licensed outposts: Osteria Mozza Los Cabos, Singapore (moving to ION Orchard, Aug 2026), Lānaʻi (Four Seasons, opened about 2025-11-03) and Washington. Spacca Tutto at Palisades Village (with Caruso and New School Hospitality) was announced in Oct 2025, and one report gives an Oct 15 opening. C https://mauinow.com/2025/11/03/restaurant-now-open-osteria-mozza-lana%ca%bbi-at-four-seasons-resort-lana%ca%bbi/ · C https://caruso.com/newsroom/press-releases/2025/a-first-look-at-spacca-tutto-caruso-nancy-silverton-unveil-vision-for-a-new-dining-destination-at-palisades-village-opening-in-2026/
**Loyalist evidence:** **None found.** There is no embed on osteriamozza.com or pizzeriamozza.com (BentoBox sites). **I could not date the start.**
**Possible pre-purchase events:** A hotel-partner opening (Lānaʻi, Nov 2025), a new LA concept with a developer partner (Spacca Tutto, 2025–26) and an international relocation (Singapore, 2026). These are out-of-market expansions, as at Grassfed and High Street (I).
**Reservations (curl):** OpenTable (`data-reservation-service="opentable"` on both sites); Toast present. C
**Decision-makers:** Nancy Silverton (chef/owner).

## 10. Chez Noir (Carmel-by-the-Sea, CA)
**Structure:** A single venue run by Jonny and Monique Black, opened Oct 2022. Michelin ★ in July 2023, kept through 2026. Jonny Black was a JBF semifinalist (2025 cycle). C https://www.montereycountynow.com/blogs/food_blog/chez-noir-chef-jonny-black-named-as-a-james-beard-award-semifinalist/article_6bf89918-d91f-11ef-9849-d736d1741b2b.html · C https://www.7x7.com/chez-noir-carmel-michelin-star-2662709650
**Loyalist evidence:** **None found** (no embed on cheznoircarmel.com, a Squarespace site). **I could not date the start.**
**Possible pre-purchase events:** Michelin ★ (2023) and JBF semifinalist (Jan 2025, judging by the article ID timestamp) (I). The Blacks have said they "want to do more in Carmel" (C https://www.ediblemontereybay.com/?p=25916 via search).
**Reservations (curl):** OpenTable (opentable.com/r/chez-noir-carmel-by-the-sea). C
**Decision-makers:** Jonny Black (chef/owner) and Monique Black (co-owner, front of house).

---

## Cross-customer patterns

Of the 10 customers, 3 have a usable dating anchor: Glendale (after Sept 2024), Mattos (by 2025-04-23) and Grassfed (by Feb 2026). High Street is bounded to an autumn. The other six are undated. Treat the counts below as directional.

| Pre-purchase event | Count | Notes |
|---|---|---|
| New venue opened or announced in the prior ~12 months | **6/10** (Glendale, High Street, Grassfed, STARR, Mozza, plus Tao in a broad sense) | This is the strongest recurring signal. The second-to-fourth venue is the sweet spot for small groups. |
| **Out-of-market expansion** (first venue in a new city) | **4/10** (High Street→DC, Grassfed→ATL, STARR→Nashville/AC, Mozza→Lānaʻi/Singapore) | Running guests across cities creates the "one profile across properties" need. |
| Hotel or developer partnership | 4/10 (High Street–AKA, Mozza–Four Seasons/Caruso, TKRG–Ty Warner, Mattos–Nine Orchard ended) | The partner usually announces 3–6 months before opening. |
| Michelin or JBF status held (not necessarily new) | **8/10** | This is a fit filter, not a trigger. It matches Loyalist's "15% of Michelin-starred restaurants" claim. |
| New private-events space or program | 3/10 (High Street Back Room/Bread Room, Grassfed ZeyZey/Rabbit Ears, Mattos events page) | Ellen Yin's quote names private events as the reason she bought. |
| New marketing or CRM person | 1–2/10 confirmed (Grassfed's Ellie Jackson) | Public job titles are thin. LinkedIn would add more, but was not scraped. |
| Reservation-platform change | 1/10 likely (Estela Tock→OpenTable; date unknown) | Platform mix: **OpenTable 6**, Resy 2 (Rose's, H&W), Tock 1 (TKRG), mixed 1 (Tao). Loyalist sits on top of all of them, so the platform does not decide fit. |
| Funding or ownership change | 2/10 (Tao–Mohari 2023; Rose's Form D 2026) | Weak trigger. |
| Portfolio contraction or consolidation | 1/10 (Mattos 2024) | Contraction can also trigger centralizing guest relations ("VIP line"). |

**Typical lag (I):** Glendale bought within about 0–12 months of opening its third venue. Grassfed was on Loyalist by opening day in Atlanta, about 8 months after the public permit. High Street's quote came within one autumn of a new-market or event-space opening. **Best estimate: purchase lands between 6 months before and 12 months after a new venue opens, and is often timed to pre-opening list-building.** Rabbit Ears' site is nothing but a Loyalist waitlist form.

**Signals detectable from public sources outside NYC:**
- **Building and permit filings:** Grassfed's Atlanta permit surfaced in press about 8 months before opening (C). Equivalent sources include city permit portals (Atlanta, Philadelphia L&I, LA LADBS).
- **State liquor boards (I):** each has a searchable licensee database: NC ABC Commission permits (Glendale/Próximo), PA PLCB license transfers (High Street; PA licenses are scarce and transfers are public, so they lead openings), FL DBPR (Miami), Georgia DOR plus City of Atlanta alcohol licenses (Füm, Rabbit Ears; "awaiting final approvals" was reported in May 2026) and CA ABC (Mozza, Chez Noir; pending applications are publicly listed). I did not query these boards in this pass. Next step: pull pending applications for known groups.
- **Hotel and developer press releases** (AKA, Four Seasons, Caruso, Ty Warner) announce F&B partners months ahead.
- **Michelin and JBF calendars:** Florida in April/May, California in summer, JBF semifinalists in late January. These events lift inbound demand and mailing-list size.
- **Website tech-stack diffs:** OpenTable/Resy/Tock widgets, plus `api.eatloyalist.com/signup/form` and `agent.eatloyalist.com` embeds. This doubles as a competitive-displacement and customer-detection scanner, run with plain curl. BentoBox email-signup sites (Rose's, Mozza) are the incumbent to displace.
- **SEC Form D** for restaurant-group LLCs (Rose's Management Group).

**Gaps:** I could not date the Loyalist start for STARR, TKRG, Tao, Rose's, Mozza or Chez Noir, and found no public Loyalist footprint for the last three. Without archive access, logo first-appearance dates are unknown. Running the Loyalist-embed scan on individual STARR, Tao and Mozza venue sites would help, and so would LinkedIn job-change data, via a compliant provider rather than scraping.
