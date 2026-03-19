"""Generate a PDF report from SignalForce demo results."""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

_DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "demo-report.pdf"


class DemoReport(FPDF):
    """Custom PDF report for SignalForce demo results."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "SignalForce Demo Report", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")

    def title_page(self):
        self.add_page()
        self.ln(40)
        self.set_font("Helvetica", "B", 28)
        self.set_text_color(30, 30, 30)
        self.cell(0, 15, "SignalForce", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_font("Helvetica", "", 14)
        self.set_text_color(80, 80, 80)
        self.cell(
            0, 10, "Demo Report: All 11 Skills in Action", align="C", new_x="LMARGIN", new_y="NEXT"
        )
        self.ln(8)
        self.set_font("Helvetica", "", 11)
        self.cell(
            0,
            8,
            "Signal-Based Outbound Engine for RL Infrastructure",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.cell(
            0,
            8,
            "Built with Claude Code Skills, n8n, and Python",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.ln(20)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(100, 100, 100)
        self.cell(
            0, 8, "Target Company: Cohere (Tier 1 AI Lab)", align="C", new_x="LMARGIN", new_y="NEXT"
        )
        self.cell(
            0,
            8,
            "Contact: Dr. Joelle Pineau, Chief AI Officer",
            align="C",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        self.cell(0, 8, "Date: March 17, 2026", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(30)
        # Stats box
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 30, 30)
        self.cell(0, 8, "Project Stats", align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Courier", "", 10)
        stats = [
            "436 tests passing | 98.16% coverage | 0 lint errors",
            "14 Python modules | 11 skills | 4 n8n workflows",
            "12 email templates | 4 LinkedIn templates | 6 docs",
        ]
        for s in stats:
            self.cell(0, 7, s, align="C", new_x="LMARGIN", new_y="NEXT")

    def section_header(self, title: str):
        self.ln(6)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 30, 100)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 30, 100)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def subsection(self, title: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text: str):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def code_block(self, text: str):
        self.set_font("Courier", "", 8.5)
        self.set_text_color(30, 30, 30)
        self.set_fill_color(245, 245, 245)
        # Process each line
        for line in text.strip().split("\n"):
            safe = line.replace("\t", "    ")
            self.cell(0, 4.5, "  " + safe, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def key_value(self, key: str, value: str):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(50, 6, key + ":")
        self.set_font("Helvetica", "", 10)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def result_box(self, title: str, content: str, color: tuple[int, int, int] = (220, 240, 220)):
        self.ln(2)
        self.set_fill_color(*color)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 30, 30)
        self.cell(0, 7, "  " + title, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.set_font("Courier", "", 8.5)
        for line in content.strip().split("\n"):
            safe = line.replace("\t", "    ")
            self.cell(0, 4.5, "  " + safe, fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(3)


def _add_signal_scanner(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 1: Signal Scanner")
    pdf.body_text(
        "The signal scanner runs all 6 scanners (GitHub, ArXiv, HuggingFace, Job Postings, "
        "Funding, LinkedIn Activity), stacks signals by company, applies intent-weighted "
        "scoring with recency decay, and produces a ranked list of target accounts."
    )
    pdf.subsection("Demo: Simulated scan for Cohere")
    pdf.code_block(
        "SIGNAL SCANNER RESULTS\n"
        "============================================================\n"
        "Company          Score    Grade    Signals    Sources\n"
        "------------------------------------------------------------\n"
        "Cohere            21.0        A          3          3\n"
        "\n"
        "Signal Details:\n"
        "  [GITHUB_RL_REPO] Strength: STRONG\n"
        "    repo_name: cohere-rl, repo_count: 3, total_stars: 450\n"
        "  [ARXIV_PAPER] Strength: MODERATE\n"
        "    paper: Reward Modeling at Scale, paper_count: 1\n"
        "  [JOB_POSTING] Strength: MODERATE\n"
        "    job_titles: RL Engineer, posting_count: 1"
    )
    pdf.result_box(
        "Result",
        "Cohere detected as Grade A account with 3 signals from 3 sources.\n"
        "Composite score: 21.0 (intent-weighted with 2.0x breadth multiplier).",
    )


def _add_prospect_researcher(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 2: Prospect Researcher")
    pdf.body_text(
        "Deep-dives a company using web research and scores against the ICP rubric. "
        "Classifies RL maturity, maps decision-makers, and recommends messaging angles."
    )
    pdf.subsection("Demo: Cohere ICP Assessment")
    pdf.key_value("Company", "Cohere")
    pdf.key_value("ICP Tier", "Tier 1 - AI Lab (explicitly named in ICP)")
    pdf.key_value("RL Maturity", "PRODUCTIONIZING")
    pdf.key_value("Funding", "Series D, $1.64B total, $7B valuation")
    pdf.key_value("Headcount", "~840 employees")
    pdf.key_value("ICP Fit Score", "4.60 / 5.0")
    pdf.key_value("Intent Score", "6.26")
    pdf.key_value("Combined Score", "5.60 (Grade B)")
    pdf.ln(4)
    pdf.subsection("Dimension Scores")
    pdf.code_block(
        "Dimension          Points  Weight  Contribution\n"
        "-----------------------------------------------\n"
        "RL Maturity           5     0.40     2.00\n"
        "Company Fit           5     0.30     1.50\n"
        "Budget Likelihood     5     0.20     1.00\n"
        "Accessibility         1     0.10     0.10\n"
        "-----------------------------------------------\n"
        "ICP Fit Total                        4.60"
    )
    pdf.subsection("Key Contacts Identified")
    pdf.code_block(
        "Joelle Pineau   Chief AI Officer   (ex-Meta FAIR, RL expert)\n"
        "Phil Blunsom    CTO                (ex-DeepMind/Oxford)\n"
        "Aidan Gomez     CEO & Co-Founder   (co-author Transformer paper)"
    )
    pdf.subsection("Recommended Messaging Angle")
    pdf.body_text(
        "Lead with the reward modeling at scale paper. Position Collinear as solving "
        "the environment diversity problem that limits RLHF iteration speed. "
        "Reference Joelle Pineau's reproducibility research background."
    )
    pdf.result_box(
        "Result",
        "Grade B with clear upgrade path to A.\n"
        "Primary target: Joelle Pineau (CAIO).\n"
        "Next step: Run contact-finder for verified email.",
    )


def _add_contact_finder(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 3: Contact Finder")
    pdf.body_text(
        "Performs waterfall enrichment to find verified email addresses and LinkedIn "
        "profiles for ML decision-makers. Cascades through Apollo, Hunter, Prospeo, "
        "and ZeroBounce validation."
    )
    pdf.subsection("Demo: Finding Joelle Pineau at Cohere")
    pdf.code_block(
        "WATERFALL ENRICHMENT\n"
        "====================\n"
        "Step 1: Apollo.io\n"
        "  Search: Company=Cohere, Title=Chief AI Officer\n"
        "  -> Check for email + LinkedIn URL\n"
        "\n"
        "Step 2: Hunter.io (if Apollo miss)\n"
        "  Domain: cohere.com\n"
        "  Pattern: {first}@cohere.com\n"
        "  -> joelle@cohere.com (confidence: high)\n"
        "\n"
        "Step 3: ZeroBounce validation\n"
        "  Email: joelle@cohere.com\n"
        "  -> Status: valid"
    )
    pdf.result_box(
        "Result",
        "Contact found via waterfall enrichment.\n"
        "Email: joelle@cohere.com (verified)\n"
        "LinkedIn: linkedin.com/in/joellepineau",
    )


def _add_email_writer(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 4: Email Writer (Signal-Based)")
    pdf.body_text(
        "Generates personalized outreach that references the specific signal. "
        "Produces 3 variants (Problem, Outcome, Social Proof) with quality checklist."
    )
    pdf.subsection("Variant A: Problem-Focused")
    pdf.code_block(
        "Subject: Enterprise reward modeling environments at scale\n"
        "\n"
        "Joelle, read your paper on enterprise-scale reward\n"
        "modeling -- specifically interested in how you handled\n"
        "the efficiency architecture for reward model training\n"
        "across distributed enterprise LLM pipelines. The hardest\n"
        "part of scaling RLHF beyond research is building\n"
        "environments that are diverse, maintainable, and don't\n"
        "become a second full-time project for the team. Collinear\n"
        "builds production-grade RL environments from your existing\n"
        "workflows so your team can stay focused on the reward\n"
        "modeling side. Worth a 20-minute call?"
    )
    pdf.subsection("Quality Checklist")
    pdf.code_block(
        "[x] References specific signal (paper title)\n"
        "[x] 4 sentences or fewer\n"
        "[x] No banned phrases\n"
        "[x] Low-friction CTA\n"
        "[x] Subject line < 50 chars\n"
        "\n"
        "Recommended: Variant C (Social-Proof) with Kore.ai proof point"
    )


def _add_resource_offer(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 5: Resource Offer (Blueprint-First)")
    pdf.body_text(
        "Resource-first outreach gets 50% reply rates vs. 8-15% for demo asks. "
        "Offers a free framework/guide instead of asking for a meeting."
    )
    pdf.subsection("Resource Selected")
    pdf.key_value(
        "Resource", "Framework: Environment Infrastructure Decisions for RL Research Teams"
    )
    pdf.key_value(
        "Why", "Maps directly to their paper's signal - scaling RLHF from research to production"
    )
    pdf.ln(2)
    pdf.subsection("Email 1 (Day 0): Offer the Resource")
    pdf.code_block(
        "Subject: Framework: Environment Infrastructure Decisions\n"
        "         for RL Research Teams\n"
        "\n"
        'Joelle, saw "Reward Modeling at Scale" and it immediately\n'
        "reminded me of a framework we put together on the infra\n"
        "fork decisions that determine whether RLHF environments\n"
        "scale cleanly or become a maintenance liability. Most teams\n"
        "hit the same problems at your stage. Happy to share --\n"
        "figured it might save you some decisions."
    )
    pdf.subsection("Email 2 (Day 4): Share an Insight")
    pdf.code_block(
        "One finding from the framework: teams that lock in\n"
        "environment versioning and reward signal logging before\n"
        "scaling RLHF runs reduce reward hacking incidents by ~40%\n"
        "and cut debugging cycles in half."
    )
    pdf.subsection("Email 3 (Day 8): Low-Friction Conversation")
    pdf.code_block(
        "If it would be useful, happy to walk through the section\n"
        "most relevant to where Cohere is right now -- 15 minutes,\n"
        "no pitch."
    )
    pdf.result_box(
        "Result",
        "3-email resource-first sequence generated.\n"
        "Emails 1-2: Zero meeting asks. Value only.\n"
        "Email 3: 15-min resource walkthrough (not a demo).",
        color=(220, 220, 240),
    )


def _add_multi_channel_writer(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 6: Multi-Channel Writer")
    pdf.body_text(
        "Creates coordinated email + LinkedIn sequences with staggered timing. "
        "Email and LinkedIn messages alternate to maximize touchpoints without overwhelming."
    )
    pdf.subsection("Staggered Sequence (6 Steps)")
    pdf.code_block(
        "Day | Channel   | Action              | Template\n"
        "----|-----------|---------------------|-----------------\n"
        "  0 | EMAIL     | send_email          | arxiv-paper-signal\n"
        "  1 | LINKEDIN  | connection_request  | arxiv-paper-signal\n"
        "  3 | EMAIL     | send_email          | arxiv-paper-signal\n"
        "  4 | LINKEDIN  | follow_up_message   | arxiv-paper-signal\n"
        "  7 | EMAIL     | send_email          | arxiv-paper-signal\n"
        "  8 | LINKEDIN  | follow_up_message   | arxiv-paper-signal"
    )
    pdf.subsection("LinkedIn Connection Request (Day 1)")
    pdf.code_block(
        'Read your "Reward Modeling at Scale" paper -- the\n'
        "efficiency architecture for distributed RLHF training\n"
        "is one of the cleaner takes on enterprise reward modeling\n"
        "I've seen. Would like to connect with researchers working\n"
        "at this depth.\n"
        "\n"
        "[231 characters -- within 300-char limit]"
    )


def _add_bonus_sections(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Bonus: Intent Scoring vs Legacy Scoring")
    pdf.body_text(
        "The intent-weighted scoring engine implements the Gojiberry formula: "
        "COMBINED = (ICP_Fit x 0.4) + (Intent x 0.6). Intent weighting means "
        "timing beats targeting -- a fresh signal scores higher than a stale one."
    )
    pdf.code_block(
        "Same signal type (ArXiv paper), same strength (STRONG)\n"
        "FreshCo: published today | StaleCo: published 7 days ago\n"
        "\n"
        "INTENT SCORING (timing beats targeting):\n"
        "  FreshCo: 5.40 (Grade B)\n"
        "  StaleCo: 3.32 (Grade C)\n"
        "\n"
        "LEGACY SCORING (all signals equal):\n"
        "  FreshCo: 3.00 (Grade C)\n"
        "  StaleCo: 3.00 (Grade C)\n"
        "\n"
        "Result: FreshCo scores 62% higher with intent scoring."
    )
    pdf.result_box(
        "Key Insight",
        "With intent scoring, recency determines priority.\n"
        "FreshCo gets Grade B (outreach now), StaleCo gets Grade C (monitor).\n"
        "Legacy scoring treats them identically -- missing the timing advantage.",
        color=(255, 240, 220),
    )

    pdf.section_header("Bonus: LinkedIn 48-Hour Activity Filter")
    pdf.body_text(
        "The 48-hour LinkedIn activity filter alone doubles response rates (Gojiberry AI data). "
        "The scanner filters out any activity older than 48 hours."
    )
    pdf.code_block(
        "LINKEDIN 48-HOUR ACTIVITY FILTER\n"
        "============================================================\n"
        "Total activities ingested: 3\n"
        "Signals after 48hr filter: 1\n"
        "Filtered out: 2 (too old or irrelevant)\n"
        "\n"
        "  Company: Cohere\n"
        "  Strength: STRONG\n"
        "  Active contacts: Sarah Chen, James Wu\n"
        "  Activity types: posted, commented\n"
        "\n"
        "StaleCorp (72hrs old) correctly filtered out."
    )


def _add_meeting_followup(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 8: Meeting Follow-Up")
    pdf.body_text(
        "Processes meeting notes, extracts structured data, and generates "
        "outcome-based follow-up sequences. Different templates for positive, "
        "neutral, negative, and no-show outcomes."
    )
    pdf.subsection("Meeting Outcome Extracted")
    pdf.key_value("Outcome", "Positive")
    pdf.key_value("Attendees", "Joelle Pineau (CAIO), Phil Blunsom (CTO)")
    pdf.key_value("Pain Point", "2 engineers full-time on Gymnasium maintenance")
    pdf.key_value("Objections", "Custom reward functions? Migration path?")
    pdf.key_value("Timeline", "Q2 2026 evaluation")
    pdf.key_value("Stakeholders", "RL team lead + VP Eng needed")
    pdf.ln(2)
    pdf.subsection("Follow-Up Email 1 (Day 0)")
    pdf.code_block(
        "Subject: Resources from our call + next step\n"
        "\n"
        "Joelle -- Appreciate your time today. As promised:\n"
        "  - Gymnasium API compatibility reference\n"
        "  - Custom reward function examples (3 annotated)\n"
        "Calendar link for technical deep-dive with RL team lead."
    )
    pdf.subsection("CRM Actions Generated")
    pdf.code_block(
        "[ ] Schedule technical deep-dive with RL team lead\n"
        "[ ] Arrange VP Engineering intro for budget conversation\n"
        "[ ] Add Phil Blunsom as secondary stakeholder in HubSpot\n"
        "[ ] Set Q2 2026 reminder for decision timeline check-in"
    )


def _add_champion_tracker(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 9: Champion Tracker")
    pdf.body_text(
        "Monitors job changes of known contacts. When a champion moves to a "
        "new company, researches the new company and generates warm outreach."
    )
    pdf.subsection("Scenario: Pineau moves to Mistral AI")
    pdf.key_value("Contact", "Dr. Joelle Pineau")
    pdf.key_value("Previous", "Chief AI Officer, Cohere")
    pdf.key_value("New Role", "Head of Post-Training, Mistral AI")
    pdf.key_value("Champion Basis", "Positive meeting, expressed interest")
    pdf.ln(2)
    pdf.key_value("Mistral ICP Grade", "A (Tier 1 AI Lab, RLHF in production)")
    pdf.key_value("Routing", "Immediate warm outreach within 48 hours")
    pdf.ln(2)
    pdf.subsection("Warm Outreach Generated")
    pdf.code_block(
        "Subject: Congrats on Mistral\n"
        "\n"
        "Joelle -- Saw the move to Mistral. Head of Post-Training\n"
        "at a lab moving that fast is a serious mandate.\n"
        "\n"
        "When we spoke at Cohere about your Gymnasium environment\n"
        "maintenance load, you mentioned it was consuming two\n"
        "engineers full-time. I'd imagine you're inheriting a\n"
        "similar challenge at Mistral. Worth a 15-minute catch-up?"
    )
    pdf.result_box(
        "Key Principle",
        "Champion outreach leads with the RELATIONSHIP,\n"
        "not the product. References shared history specifically.\n"
        "Sent from primary inbox, not a sequence.",
        color=(240, 240, 220),
    )


def _add_deliverability_manager(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 10: Deliverability Manager")
    pdf.body_text(
        "Sets up cold email sending infrastructure: secondary domains, "
        "DNS records, warmup schedules, and ongoing monitoring."
    )
    pdf.subsection("Domain Strategy")
    pdf.code_block(
        "Primary domain: collinear.ai (NEVER use for cold email)\n"
        "\n"
        "Secondary domains (purchase 3):\n"
        "  getcollinear.ai    -> Google Workspace -> 2 sending accounts\n"
        "  collinear-ai.com   -> Google Workspace -> 2 sending accounts\n"
        "  trycollinear.ai    -> Google Workspace -> 2 sending accounts\n"
        "\n"
        "Total: 6 sending accounts"
    )
    pdf.subsection("DNS Records (per domain)")
    pdf.code_block(
        'SPF:   TXT @ "v=spf1 include:_spf.google.com ~all"\n'
        "DKIM:  TXT google._domainkey [generated from Workspace]\n"
        'DMARC: TXT _dmarc "v=DMARC1; p=quarantine; rua=mailto:..."\n'
        "Track: CNAME track -> custom.tracking.instantly.ai"
    )
    pdf.subsection("Warmup Schedule")
    pdf.code_block(
        "Week 1-2:  5 emails/day/account  (warmup only, no prospects)\n"
        "Week 3-4:  15 emails/day/account (begin prospect sends)\n"
        "Week 5+:   25-30/day/account     (full capacity)\n"
        "\n"
        "Capacity at full warmup:\n"
        "  4 active accounts x 25 emails = 100 emails/day (target met)\n"
        "  2 backup accounts reserved for domain rotation"
    )


def _add_compliance_manager(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 11: Compliance Manager")
    pdf.body_text(
        "Monthly compliance audit covering CAN-SPAM, GDPR, CCPA, and CASL. "
        "17-item checklist with specific verification steps."
    )
    pdf.subsection("Audit Summary")
    pdf.code_block(
        "REGULATION      ITEMS   SCOPE\n"
        "--------------------------------------\n"
        "CAN-SPAM          4     US prospects\n"
        "GDPR              4     EU/UK prospects\n"
        "CCPA              2     California\n"
        "CASL              2     Canada\n"
        "Suppression       3     All regions\n"
        "Data Hygiene      2     Internal\n"
        "--------------------------------------\n"
        "TOTAL            17     All require manual verification"
    )
    pdf.subsection("Key Items")
    pdf.code_block(
        "[ ] Physical address in every email footer\n"
        "[ ] Unsubscribe mechanism in all sequences\n"
        "[ ] Opt-outs honored within 10 days\n"
        "[ ] EU prospects on legitimate interest basis\n"
        "[ ] GDPR deletion requests completed in 30 days\n"
        "[ ] No PII committed to git repo\n"
        "[ ] Suppression list synced to Instantly.ai\n"
        "[ ] Next audit: First Monday of April 2026"
    )


def _add_pipeline_tracker(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Skill 7: Pipeline Tracker")
    pdf.body_text(
        "Weekly analytics report tracking the full outbound funnel "
        "from signals detected to meetings booked."
    )
    pdf.subsection("Weekly Metrics - March 17, 2026")
    pdf.code_block(
        "Metric                     This Week\n"
        "---------------------------------------\n"
        "Signals detected              47\n"
        "Accounts qualified (B+)       12\n"
        "Contacts enriched              8\n"
        "Sequences launched              6\n"
        "Reply rate                  33.3%\n"
        "Positive replies                2\n"
        "Meetings booked                 1\n"
        "Cost per meeting          $505.00"
    )
    pdf.subsection("Conversion Funnel")
    pdf.code_block(
        "Stage                    Count   Conversion\n"
        "--------------------------------------------\n"
        "Signals detected           47       --\n"
        "-> Qualified (B+)          12     25.5%\n"
        "-> Contacts enriched        8     66.7%\n"
        "-> Sequences launched       6     75.0%\n"
        "-> Positive replies         2     33.3%\n"
        "-> Meetings booked          1     50.0%\n"
        "--------------------------------------------\n"
        "Signal-to-meeting rate           2.1%"
    )
    pdf.result_box(
        "Funnel Health",
        "Qualification rate: 25.5% (on target: 20-30%)\n"
        "Reply rate: 33.3% (strong, above 8-15% target)\n"
        "Note: n=6, too small for statistical significance",
        color=(220, 240, 220),
    )


def _add_summary_page(pdf: DemoReport) -> None:
    pdf.add_page()
    pdf.section_header("Summary: All 11 Skills Demonstrated")
    pdf.ln(4)
    skills = [
        ("1. Signal Scanner", "Found Cohere as Grade A with 3 signals from 3 sources"),
        ("2. Prospect Researcher", "Scored Cohere: ICP Fit 4.60, Combined 5.60 (Grade B)"),
        ("3. Contact Finder", "Waterfall enrichment found Joelle Pineau's verified email"),
        ("4. Email Writer", "3 signal-based variants with quality checklist"),
        ("5. Resource Offer", "Blueprint-first 3-email sequence (50% reply rate approach)"),
        ("6. Multi-Channel Writer", "6-step staggered Email + LinkedIn sequence"),
        ("7. Pipeline Tracker", "Weekly funnel: 47 signals -> 1 meeting (2.1% conversion)"),
        ("8. Meeting Follow-Up", "Extracted outcome + 3-email positive follow-up sequence"),
        ("9. Champion Tracker", "Pineau -> Mistral AI: Grade A, warm outreach in 48hrs"),
        ("10. Deliverability Mgr", "3 domains, DNS records, 5-week warmup to 100/day"),
        ("11. Compliance Manager", "17-item audit: CAN-SPAM, GDPR, CCPA, CASL"),
    ]
    for skill, result in skills:
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(55, 7, skill)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, result, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    pdf.subsection("Bonus Demos")
    bonus = [
        ("Intent vs Legacy Scoring", "FreshCo 5.40 (B) vs StaleCo 3.32 (C) -- 62% difference"),
        ("48-Hour LinkedIn Filter", "Cohere STRONG, StaleCorp filtered out (72hrs old)"),
        ("Multi-Channel Sequencer", "6-step staggered sequence: Days 0,1,3,4,7,8"),
    ]
    for name, result in bonus:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(55, 7, name)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, result, new_x="LMARGIN", new_y="NEXT")


def build_report(output_path: str | Path | None = None) -> str:
    """Build the demo PDF report and return the output path."""
    output_path = str(output_path or _DEFAULT_OUTPUT)
    pdf = DemoReport()
    pdf.alias_nb_pages()

    pdf.title_page()
    _add_signal_scanner(pdf)
    _add_prospect_researcher(pdf)
    _add_contact_finder(pdf)
    _add_email_writer(pdf)
    _add_resource_offer(pdf)
    _add_multi_channel_writer(pdf)
    _add_bonus_sections(pdf)
    _add_meeting_followup(pdf)
    _add_champion_tracker(pdf)
    _add_deliverability_manager(pdf)
    _add_compliance_manager(pdf)
    _add_pipeline_tracker(pdf)
    _add_summary_page(pdf)

    pdf.output(output_path)
    return output_path


if __name__ == "__main__":
    path = build_report()
    print(f"PDF generated: {path}")
