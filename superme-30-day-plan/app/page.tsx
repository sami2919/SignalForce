const weeks = [
  {
    week: "Week 1",
    title: "Define the network wedge",
    goal: "Understand which professionals make SuperMe more valuable first, and why.",
    actions: [
      "Align with Casey and Ludo on the first version of network quality",
      "Review current profiles and note where expertise feels specific vs generic",
      "Talk to a handful of current or target users about what would make a profile worth saving, sharing, or asking questions of",
      "Define what a high signal professional means for SuperMe in practical terms",
      "Identify 3 initial operator segments worth targeting and why each could create pull",
    ],
    examples: [
      "AI GTM operators",
      "early stage product builders",
      "technical founders who sell",
      "RevOps and growth engineers",
      "design partners with strong internal playbooks",
    ],
    output:
      "A simple ICP for the first 100 high value professionals, plus a profile quality rubric that can guide sourcing and onboarding.",
  },
  {
    week: "Week 2",
    title: "Build the sourcing machine",
    goal: "Find people who make the network stronger.",
    actions: [
      "Build a list of 100 target operators",
      "Rank them by expertise, artifact quality, network pull, and willingness to share",
      "Use signals like posts, GitHub, podcasts, talks, newsletters, job history, community activity, and founder mentions",
      "Write outreach that references a person's actual work, not just their title",
      "Test 3 outreach angles and track which one earns thoughtful replies",
    ],
    output:
      "A ranked operator list, scoring model, and outreach system Casey can inspect and improve.",
  },
  {
    week: "Week 3",
    title: "Turn onboarding into product learning",
    goal: "Make every new professional improve the product.",
    actions: [
      "Interview onboarded operators about what knowledge they actually want represented",
      "Track where profiles feel useful vs generic",
      "Identify missing artifact types, weak prompts, bad summaries, or unclear value moments",
      "Feed insights back into profile creation, search, recommendations, and onboarding",
      "Capture the exact language operators use to describe their edge, playbooks, and hard-won judgment",
    ],
    output:
      "A product feedback loop where every onboarded operator improves profile creation, discovery, and AI usefulness.",
  },
  {
    week: "Week 4",
    title: "Systematize GTM and community",
    goal: "Turn the process into repeatable infrastructure.",
    actions: [
      "Create a lightweight CRM or GTM dashboard",
      "Track source, segment, artifact quality, activation, referrals, and product feedback",
      "Build a repeatable onboarding playbook",
      "Create a community loop where the best operators attract other operators",
      "Package the learnings into a weekly operating rhythm for sourcing, onboarding, product feedback, and follow-up",
    ],
    output:
      "A repeatable system for adding people who make SuperMe more valuable, not just larger.",
  },
];

const loopSteps = [
  {
    title: "Find high signal professionals",
    body: "Start with people whose work already shows judgment, taste, and repeatable expertise.",
  },
  {
    title: "Capture real artifacts",
    body: "Pull in playbooks, talks, writing, projects, templates, and examples of how they actually operate.",
  },
  {
    title: "Turn that into useful profiles",
    body: "Make the profile answer better questions than a LinkedIn page could.",
  },
  {
    title: "Learn what creates value",
    body: "Watch what users save, ask, share, search for, and come back to.",
  },
  {
    title: "Use the network to attract more signal",
    body: "Give great operators a reason to invite other great operators.",
  },
];

const metrics = [
  {
    title: "Network quality",
    items: [
      "Number of high signal professionals added",
      "Referral rate from existing professionals",
      "Segment density by operator type",
      "Percentage of profiles with strong artifacts",
    ],
  },
  {
    title: "Product quality",
    items: [
      "Profile usefulness score",
      "Search or recommendation success rate",
      "User saved or shared profiles",
      "Questions answered successfully by profile AI",
    ],
  },
  {
    title: "GTM quality",
    items: [
      "Outreach reply rate",
      "Activation rate",
      "Time from sourced to onboarded",
      "Repeatable playbook created",
    ],
  },
];

const emailHref =
  "mailto:casey@superme.ai?subject=SuperMe%2030%20Day%20Plan&body=Hey%20Casey%2C%20I%20made%20this%20for%20you%20after%20reading%20the%20SuperMe%20hiring%20post.%20I%20tried%20to%20show%20how%20I%E2%80%99d%20think%20about%20making%20the%20product%20better%20and%20the%20network%20stronger%20at%20the%20same%20time.%20Would%20love%20to%20chat%20if%20this%20is%20directionally%20useful.";

function SectionHeader({
  label,
  title,
}: {
  label?: string;
  title: string;
}) {
  return (
    <div className="mb-7">
      {label ? (
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-accent">
          {label}
        </p>
      ) : null}
      <h2 className="text-2xl font-semibold tracking-tight text-ink sm:text-3xl">
        {title}
      </h2>
    </div>
  );
}

function CheckList({ items }: { items: string[] }) {
  return (
    <ul className="space-y-2.5 text-sm leading-6 text-muted">
      {items.map((item) => (
        <li key={item} className="flex gap-3">
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  );
}

export default function Home() {
  return (
    <main className="min-h-screen px-5 py-6 sm:px-8 sm:py-10">
      <div className="mx-auto max-w-[900px]">
        <header className="mb-16 rounded-lg border border-line bg-paper/85 p-6 shadow-memo sm:p-8">
          <div className="mb-12 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">
              Proof of work for Casey at SuperMe
            </p>
            <a
              href="https://github.com/sami2919"
              className="text-sm font-medium text-muted underline decoration-line underline-offset-4 transition hover:text-ink"
            >
              github.com/sami2919
            </a>
          </div>

          <div className="max-w-[760px]">
            <h1 className="text-4xl font-semibold tracking-tight text-ink sm:text-6xl">
              Making SuperMe Better and the Network Stronger
            </h1>
            <p className="mt-6 max-w-[690px] text-lg leading-8 text-muted sm:text-xl">
              Casey, I put this together as a concrete first 30 day plan for
              turning great professionals into a stronger product, stronger
              network, and stronger GTM loop.
            </p>
            <p className="mt-5 text-sm font-medium text-ink">
              Prepared for Casey by Sami Rahman
            </p>
          </div>

          <div className="mt-10 flex flex-col gap-3 sm:flex-row">
            <a
              href="#plan"
              className="inline-flex items-center justify-center rounded-md bg-ink px-5 py-3 text-sm font-semibold text-white transition hover:bg-accent"
            >
              View 30 Day Plan
            </a>
            <a
              href="https://github.com/sami2919"
              className="inline-flex items-center justify-center rounded-md border border-line bg-white px-5 py-3 text-sm font-semibold text-ink transition hover:border-ink"
            >
              GitHub
            </a>
          </div>
        </header>

        <div className="space-y-16">
          <section>
            <SectionHeader title="Why this role clicked" />
            <div className="space-y-4 text-lg leading-8 text-muted">
              <p>
                Casey, your post stood out because the role is not really one
                lane. It reads like product, GTM, community, systems, and taste
                all bleeding into each other.
              </p>
              <p>
                That is the kind of work I like. Build the thing, figure out
                who needs it, get it in front of them, learn from the reaction,
                and tighten the system.
              </p>
              <p>
                My read is that SuperMe does not just need someone to execute
                tasks. It needs someone who can notice where product quality,
                network quality, and go-to-market quality reinforce each other,
                then turn that into a weekly operating system.
              </p>
            </div>
          </section>

          <section>
            <SectionHeader title="My read on the problem" />
            <p className="mb-6 text-lg leading-8 text-ink">
              SuperMe gets stronger when the right professionals join, but only
              if their expertise becomes usable inside the product.
            </p>
            <p className="mb-6 text-base leading-7 text-muted">
              The hard part is not just recruiting impressive people. It is
              converting their judgment, artifacts, and lived operating
              experience into something users can search, understand, trust, and
              come back to.
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              {[
                "The network needs high signal people, not just more people",
                "The product needs real artifacts of expertise, not generic profiles",
                "GTM should create product learning, not just pipeline",
              ].map((item) => (
                <div
                  key={item}
                  className="rounded-lg border border-line bg-white p-5 text-sm font-medium leading-6 text-ink shadow-memo"
                >
                  {item}
                </div>
              ))}
            </div>
          </section>

          <section id="plan" className="scroll-mt-8">
            <SectionHeader label="First 30 days" title="The plan" />
            <div className="grid gap-4">
              {weeks.map((week) => (
                <article
                  key={week.week}
                  className="rounded-lg border border-line bg-white p-5 shadow-memo sm:p-6"
                >
                  <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">
                        {week.week}
                      </p>
                      <h3 className="mt-2 text-xl font-semibold tracking-tight text-ink">
                        {week.title}
                      </h3>
                    </div>
                    <p className="max-w-[310px] text-sm leading-6 text-muted">
                      <span className="font-semibold text-ink">Goal:</span>{" "}
                      {week.goal}
                    </p>
                  </div>

                  <div className="grid gap-6 sm:grid-cols-[1fr_260px]">
                    <div>
                      <p className="mb-3 text-sm font-semibold text-ink">
                        Actions
                      </p>
                      <CheckList items={week.actions} />
                    </div>
                    <div className="rounded-md border border-line bg-soft p-4">
                      {week.examples ? (
                        <>
                          <p className="mb-3 text-sm font-semibold text-ink">
                            Example segments
                          </p>
                          <div className="mb-5 flex flex-wrap gap-2">
                            {week.examples.map((example) => (
                              <span
                                key={example}
                                className="rounded-full border border-line bg-paper px-3 py-1 text-xs font-medium text-muted"
                              >
                                {example}
                              </span>
                            ))}
                          </div>
                        </>
                      ) : null}
                      <p className="text-sm leading-6 text-muted">
                        <span className="font-semibold text-ink">Output:</span>{" "}
                        {week.output}
                      </p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section>
            <SectionHeader title="The loop I'd try to build" />
            <div className="rounded-lg border border-line bg-white p-5 shadow-memo sm:p-6">
              <ol className="grid gap-3 sm:grid-cols-5">
                {loopSteps.map((step, index) => (
                  <li
                    key={step.title}
                    className="min-h-[170px] rounded-md border border-line bg-paper p-4"
                  >
                    <span className="text-xs font-semibold uppercase tracking-[0.16em] text-accent">
                      Step {index + 1}
                    </span>
                    <p className="mt-3 text-sm font-medium leading-6 text-ink">
                      {step.title}
                    </p>
                    <p className="mt-2 text-xs leading-5 text-muted">
                      {step.body}
                    </p>
                  </li>
                ))}
              </ol>
              <p className="mt-6 border-t border-line pt-5 text-lg leading-8 text-ink">
                The goal is not just more users. The goal is a network where
                every great professional makes the product smarter.
              </p>
            </div>
          </section>

          <section>
            <SectionHeader title="How I would measure it" />
            <p className="mb-6 max-w-[720px] text-base leading-7 text-muted">
              I would keep the dashboard small at first. The point is to learn
              whether the network is becoming more useful, whether the product
              is representing expertise better, and whether GTM is producing
              product signal instead of just activity.
            </p>
            <div className="grid gap-4 sm:grid-cols-3">
              {metrics.map((group) => (
                <article
                  key={group.title}
                  className="rounded-lg border border-line bg-white p-5 shadow-memo"
                >
                  <h3 className="mb-4 text-base font-semibold text-ink">
                    {group.title}
                  </h3>
                  <CheckList items={group.items} />
                </article>
              ))}
            </div>
          </section>

          <section>
            <SectionHeader title="Why I can help" />
            <div className="space-y-4 text-lg leading-8 text-muted">
              <p>I have been doing pieces of this already.</p>
              <p>
                At Circuit AI, I worked across product, demos, customer
                discovery, GTM workflows, and AI systems. With ProspectNav and
                SignalForce, I built systems for finding high intent people,
                scoring signals, and turning that into useful workflow
                infrastructure.
              </p>
              <p>
                The common thread has been translating messy external signals
                into something useful for a team: who to talk to, why now, what
                they care about, and what should happen next.
              </p>
              <p>
                SuperMe feels like the same kind of messy, high leverage
                problem. The product, network, community, and GTM motion are all
                connected. That is what makes it interesting.
              </p>
            </div>
          </section>

          <section className="rounded-lg border border-line bg-ink p-6 text-white shadow-memo sm:p-8">
            <p className="text-2xl font-semibold tracking-tight">
              If this is directionally useful, I'd love to talk.
            </p>
            <a
              href={emailHref}
              className="mt-6 inline-flex rounded-md bg-white px-5 py-3 text-sm font-semibold text-ink transition hover:bg-soft"
            >
              Email Casey
            </a>
          </section>
        </div>

        <footer className="py-10 text-center text-sm text-muted">
          Sami Rahman · Builder operator · AI systems, product, and GTM
        </footer>
      </div>
    </main>
  );
}
