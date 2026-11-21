import { Link } from 'react-router-dom';

export default function EnquirySuccess({ result, onReset, resetLabel = 'Send another' }) {
  return (
    <div className="success">
      <div className="success__icon" aria-hidden="true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>
      </div>
      <h2>Thank you{result.contact ? `, ${result.contact.split(' ')[0]}` : ''}.</h2>
      <p>
        Your enquiry is registered as <span className="ref">{result.ref || `#${result.id}`}</span>. An advisor will call
        {result.phone ? <> you on <strong>{result.phone}</strong></> : ' you'} within two working hours.
      </p>
      <div className="actions">
        {result.signed_in
          ? <Link to="/account" className="btn btn--primary">Track it in my account</Link>
          : <Link to="/signup" className="btn btn--primary">Create an account to track it</Link>}
        <Link to="/" className="link">Back to home</Link>
        {onReset && <button type="button" className="link" style={{ background: 'none', border: 0, cursor: 'pointer' }} onClick={onReset}>{resetLabel}</button>}
      </div>
    </div>
  );
}
