import React from "react";
import {
  Badge,
  Button,
  Card,
  Notice,
  StatCard,
} from "../design-system/index.js";
import "./screens.css";

const steps = [
  { n: "01", title: "Set the interview", body: "Choose technical, HR, behavioural, or role-based practice and a target role." },
  { n: "02", title: "Answer in a calm room", body: "A focused space with a timer, transcript, and controls that stay quiet while you speak." },
  { n: "03", title: "Review structured feedback", body: "See a score breakdown, recommendations, and a report you can revisit." },
];

const audiences = [
  { role: "Students", body: "Practise on demand and watch readiness improve attempt by attempt." },
  { role: "Teachers", body: "Support assigned students with shared feedback and progress context." },
  { role: "Coordinators", body: "Understand readiness across classes, courses, and semesters." },
  { role: "Admins", body: "Manage accounts, roles, and institutional configuration." },
];

export default function LandingPage({ onLogin, onSignup }) {
  return (
    <div className="qm qm-landing">
      <header className="qm-landing__nav">
        <a className="qm-landing__brand" href="/">
          <span className="qm-appshell__mark" aria-hidden="true" />
          <span>QueMe</span>
        </a>
        <nav className="qm-landing__links" aria-label="Sections">
          <a href="#how">How it works</a>
          <a href="#audiences">Who it is for</a>
        </nav>
        <div className="qm-row">
          <Button variant="ghost" size="sm" onClick={onLogin}>Log in</Button>
          <Button size="sm" onClick={onSignup}>Get started</Button>
        </div>
      </header>

      <main>
        <section className="qm-landing__hero qm-content">
          <div className="qm-landing__hero-copy">
            <Badge tone="accent" size="sm" dot>Interview practice platform</Badge>
            <h1 className="qm-landing__brand-title">QueMe</h1>
            <h2 className="qm-landing__headline">Practise interviews with a calm room and clear feedback.</h2>
            <p className="qm-landing__sub">
              QueMe helps students rehearse real interview scenarios and turn each attempt into
              structured, actionable feedback — with progress that stays visible.
            </p>
            <div className="qm-row qm-landing__cta">
              <Button size="lg" onClick={onSignup}>Start practising</Button>
              <Button variant="secondary" size="lg" onClick={onLogin}>I have an account</Button>
            </div>
            <p className="qm-landing__reassure">No credit card. Practice feedback is for learning, not hiring decisions.</p>
          </div>

          <aside className="qm-landing__preview">
            <p className="qm-landing__preview-kicker">Institutional workspace</p>
            <h2>Practice records appear here after your first assigned interview.</h2>
            <p className="qm-landing__preview-note">Access is limited to your authorized course and class scope.</p>
          </aside>
        </section>

        <section className="qm-landing__stats qm-content" aria-label="Platform focus">
          <StatCard label="Interview formats" value="4" hint="Technical, HR, behavioural, role based" />
          <StatCard label="Feedback signals" value="6" hint="Concept, relevance, completeness, length" />
          <StatCard label="Calm room" value="1" hint="One primary action per step" />
        </section>

        <section id="how" className="qm-landing__section qm-content">
          <div className="qm-landing__section-head">
            <p className="qm-eyebrow">How it works</p>
            <h2>Three calm steps from setup to feedback.</h2>
          </div>
          <div className="qm-grid qm-grid--3">
            {steps.map((step) => (
              <Card key={step.n} className="qm-landing__step" interactive>
                <span className="qm-landing__step-num" aria-hidden="true">{step.n}</span>
                <h3>{step.title}</h3>
                <p className="qm-muted">{step.body}</p>
              </Card>
            ))}
          </div>
        </section>

        <section id="audiences" className="qm-landing__section qm-content">
          <div className="qm-landing__section-head">
            <p className="qm-eyebrow">Who it is for</p>
            <h2>Built for the whole department.</h2>
          </div>
          <div className="qm-grid qm-grid--4">
            {audiences.map((audience) => (
              <Card key={audience.role} className="qm-landing__audience">
                <h3>{audience.role}</h3>
                <p className="qm-muted">{audience.body}</p>
              </Card>
            ))}
          </div>
        </section>

        <section className="qm-landing__notice qm-content">
          <Notice tone="amber" title="Prototype status">
            Question generation, speech analysis, and institutional data access are not connected in
            this build. Screens show honest empty states until real services are configured.
          </Notice>
        </section>
      </main>

      <footer className="qm-landing__footer qm-content">
        <span className="qm-muted">QueMe · Virtual interview practice</span>
        <div className="qm-row">
          <a href="/login">Log in</a>
          <a href="/signup">Create account</a>
        </div>
      </footer>
    </div>
  );
}
