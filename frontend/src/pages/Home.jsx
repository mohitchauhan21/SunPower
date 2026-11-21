import { Link } from 'react-router-dom';
import MaskedHeading from '../components/reactbits/MaskedHeading.jsx';
import ScrollStack, { ScrollStackItem } from '../components/reactbits/ScrollStack.jsx';
import AccordionGallery from '../components/reactbits/AccordionGallery.jsx';
import Reveal from '../components/ui/Reveal.jsx';
import { PACKAGES } from '../solar.js';
import { inr } from '../api.js';

const STATS = [
  { value: '₹78,000', label: 'Maximum PM Surya Ghar subsidy' },
  { value: '1–5 kW', label: 'On-grid and battery systems' },
  { value: '20 years', label: 'Panel warranty, tracked by serial' },
  { value: '2 hours', label: 'Call-back after you enquire' }
];

const Icon = ({ d }) => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={d} />
  </svg>
);

const FEATURES = [
  { icon: 'M3 11l9-7 9 7M5 10v10h14V10', title: 'Free roof survey', text: 'An engineer measures shadow-free area, roof direction and cable runs before any price is fixed.' },
  { icon: 'M4 7h16M4 12h16M4 17h10', title: 'Subsidy, handled', text: 'We file your PM Surya Ghar application and follow it through DISCOM inspection to disbursal.' },
  { icon: 'M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z', title: 'Serial-tracked warranty', text: 'Every inverter, battery and panel batch is logged against your home the day it is delivered.' },
  { icon: 'M14.7 6.3a4 4 0 00-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 005.4-5.4l-2.5 2.5-2.5-2.5z', title: 'Our own crew', text: 'Trained SunPower technicians install, test generation on site and hand over with your signature.' },
  { icon: 'M3 12h4l3 8 4-16 3 8h4', title: 'Track it live', text: 'Follow your installation, warranties and service requests in your customer portal.' },
  { icon: 'M12 8v4l3 2M21 12a9 9 0 11-18 0 9 9 0 0118 0z', title: 'Service in days', text: 'Raise a complaint online. Warranty repairs are free, and you confirm the fix before we close it.' }
];

const STEPS = [
  { title: 'Tell us about your home.', text: 'Share your bill or monthly units. An advisor calls you back within two hours to check your roof and grid connection.', meta: 'Takes about 30 seconds' },
  { title: 'We survey your roof.', text: 'A free visit records usable area, tilt, direction and shading, so your system is sized to what your roof can really give.', meta: 'Free, no obligation' },
  { title: 'Get a fixed-price quote.', text: 'One package covers panels, inverter, structure, wiring, installation and paperwork, with the subsidy shown up front.', meta: 'Subsidy filed for you' },
  { title: 'Switch on. Stay covered.', text: 'Our crew installs and tests on site. Your warranties start automatically, and service is a message away.', meta: '20-year panel warranty' }
];

const GALLERY = [
  { image: '/img/home-rooftop.jpg', label: 'Independent homes · 2–5 kW', link: '/estimate' },
  { image: '/img/city-rooftops.jpg', label: 'Apartments & societies', link: '/quote' },
  { image: '/img/crew-installing.jpg', label: 'Installed by our own crew', link: '/quote' },
  { image: '/img/panel-rows.jpg', label: 'Flat RCC roofs', link: '/estimate' },
  { image: '/img/commercial-array.jpg', label: 'Shops, offices & factories', link: '/quote' }
];

export default function Home() {
  return (
    <>
      {/* HERO */}
      <section className="hero">
        <div className="wrap">
          <Reveal>
            <span className="eyebrow">SunPower Rooftop Solar</span>
            <h1 className="display">Sunlight,<br />well spent.</h1>
            <p className="lead">Rooftop solar for Ahmedabad homes. Surveyed, installed and serviced by one team, with the government subsidy handled for you.</p>
            <div className="actions">
              <Link to="/quote" className="btn btn--primary">Book a free survey</Link>
              <Link to="/estimate" className="link">Estimate your savings</Link>
            </div>
          </Reveal>
          <Reveal className="hero__media" delay={150}>
            <img src="/img/hero-rooftop-sunrise.jpg" alt="Rows of solar panels on a rooftop at sunrise" width="1600" height="1067" fetchpriority="high" />
          </Reveal>
        </div>
      </section>

      {/* STATS */}
      <section className="section--tight">
        <div className="wrap stats">
          {STATS.map((s, i) => (
            <Reveal key={s.label} delay={i * 80}>
              <div className="stat__value">{s.value}</div>
              <div className="stat__label">{s.label}</div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section className="section section--alt">
        <div className="wrap">
          <div className="section__head">
            <MaskedHeading
              text="Made for Indian rooftops."
              src="/img/panel-closeup.jpg"
              tag="h2"
              weight={700}
              textScale={0.075}
              reveal="rise"
            />
            <p className="lead">Everything from the first call to the last service visit, done properly.</p>
          </div>
          <div className="grid grid--3">
            {FEATURES.map((f, i) => (
              <Reveal key={f.title} className="card feature" delay={(i % 3) * 80}>
                <span className="feature__icon"><Icon d={f.icon} /></span>
                <h3>{f.title}</h3>
                <p>{f.text}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="section" style={{ paddingBottom: 0 }}>
        <div className="wrap">
          <div className="section__head">
            <span className="eyebrow">How it works</span>
            <h2 className="headline">Four steps to switched on.</h2>
          </div>
        </div>
        <div className="wrap wrap--narrow">
          <ScrollStack useWindowScroll smoothScroll={false} itemDistance={120} itemStackDistance={22} stackPosition="18%" baseScale={0.9} itemScale={0.03} dimAmount={0.12}>
            {STEPS.map((s, i) => (
              <ScrollStackItem key={s.title}>
                <div className="step-card">
                  <div>
                    <span className="step-card__n">Step {i + 1}</span>
                    <h3>{s.title}</h3>
                    <p>{s.text}</p>
                  </div>
                  <span className="step-card__meta">{s.meta}</span>
                </div>
              </ScrollStackItem>
            ))}
          </ScrollStack>
        </div>
      </section>

      {/* PACKAGES */}
      <section className="section section--alt">
        <div className="wrap">
          <div className="section__head">
            <span className="eyebrow">Packages</span>
            <h2 className="headline">Which size fits your home?</h2>
            <p className="lead">One kilowatt of panels makes about 120 units a month.</p>
          </div>
          <div className="grid grid--4">
            {PACKAGES.map((p, i) => (
              <Reveal key={p.kw} className="card pack" delay={i * 80}>
                <div className="pack__kw">{p.kw} kW</div>
                <div className="pack__units">{p.units} / month</div>
                <p className="pack__desc">{p.desc}</p>
                <div className="pack__rows">
                  <div><span className="muted">Price</span><span>{inr(p.cost)}</span></div>
                  <div><span className="muted">Subsidy</span><span className="good">− {inr(p.subsidy)}</span></div>
                  <div className="pack__net"><span>You pay</span><span>{inr(p.net)}</span></div>
                </div>
                <Link to={`/estimate?units=${p.kw * 120}`} className="link">See savings</Link>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* INSTALLATIONS */}
      <section className="section">
        <div className="wrap">
          <div className="section__head">
            <span className="eyebrow">Installations</span>
            <h2 className="headline">For every kind of rooftop.</h2>
            <p className="lead">Homes, housing societies and businesses across Ahmedabad.</p>
          </div>
          <AccordionGallery items={GALLERY} height={460} radius={24} gap={12} accentColor="#ffffff" overlayColor="#1d1d1f" grayscale={false} tilt={0} />
        </div>
      </section>

      {/* CTA */}
      <section className="section section--alt cta">
        <div className="wrap">
          <Reveal>
            <h2 className="headline">See what your roof can do.</h2>
            <p className="lead">Enter your monthly bill and get a system size, savings and payback in seconds.</p>
            <div className="actions">
              <Link to="/estimate" className="btn btn--primary">Estimate my savings</Link>
              <Link to="/quote" className="link">Or request a quote</Link>
            </div>
          </Reveal>
        </div>
      </section>
    </>
  );
}
