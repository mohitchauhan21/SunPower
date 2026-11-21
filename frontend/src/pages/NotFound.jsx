import { Link } from 'react-router-dom';
import FuzzyText from '../components/reactbits/FuzzyText.jsx';

export default function NotFound() {
  return (
    <section className="nf wrap">
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 24 }}>
        <FuzzyText fontSize="clamp(5rem, 16vw, 10rem)" fontWeight={700} color="#1d1d1f" baseIntensity={0.12} hoverIntensity={0.35}>
          404
        </FuzzyText>
      </div>
      <h1 className="title">This page is in the shade.</h1>
      <p className="lead" style={{ margin: '12px auto 28px', maxWidth: 480 }}>The page you’re looking for doesn’t exist or has moved.</p>
      <Link to="/" className="btn btn--primary">Back to home</Link>
    </section>
  );
}
