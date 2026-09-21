import React, { useEffect, useRef, useState } from 'react';

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
const examples = [
  'Which city has the most customers?',
  'What is considered a high-value claim?',
  'How many high-value claims are in the database?',
  'How many claims require high-risk review because of their value?',
];
const documents = ['Claims Policy', 'Underwriting Guidelines', 'Product Guide', 'Claims Procedure'];

function DocumentIcon() {
  return <svg width="15" height="17" viewBox="0 0 15 17" fill="none" aria-hidden="true"><path d="M9 1H2v15h11V5L9 1Z M9 1v4h4 M5 9h5 M5 12h5" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" /></svg>;
}

// Render the agent's common emphasis safely, without interpreting HTML.
function AnswerText({ text }) {
  return text.split(/(\*\*[^*]+\*\*|\*[^*\n]+\*)/g).map((part, index) => {
    if (part.startsWith('**')) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith('*')) return <em key={index}>{part.slice(1, -1)}</em>;
    return part;
  });
}

export default function App() {
  const [health, setHealth] = useState('checking');
  const [question, setQuestion] = useState('');
  const [submittedQuestion, setSubmittedQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const pending = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    fetch(`${API_URL}/health`, { signal: controller.signal })
      .then(async response => {
        const data = await response.json();
        setHealth(response.ok && data.status === 'online' ? 'online' : 'offline');
      })
      .catch(() => setHealth('offline'))
      .finally(() => clearTimeout(timeout));
    return () => { clearTimeout(timeout); controller.abort(); };
  }, []);

  async function submitQuestion(value) {
    const cleaned = value.trim();
    if (!cleaned || pending.current) return;
    pending.current = true;
    setQuestion(cleaned);
    setSubmittedQuestion(cleaned);
    setLoading(true);
    setResult(null);
    setError('');
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 180000);
    try {
      const response = await fetch(`${API_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: cleaned }),
        signal: controller.signal,
      });
      setHealth('online');
      if (!response.ok) {
        setError('The agent could not complete your question. Please try again in a moment.');
        return;
      }
      const data = await response.json();
      if (typeof data.answer !== 'string' || !(data.sql === null || typeof data.sql === 'string') ||
          !Array.isArray(data.sources) || !data.sources.every(source => typeof source === 'string')) {
        setError('We could not read the agent’s response. Please try again.');
        return;
      }
      setResult(data);
    } catch (failure) {
      setError(failure.name === 'AbortError'
        ? 'This question is taking longer than expected. Please try again.'
        : 'Unable to reach the agent. Check that the backend is running and try again.');
      setHealth('offline');
    } finally {
      clearTimeout(timeout);
      pending.current = false;
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Insurance data and knowledge">
        <div className="brand"><span className="brand-mark" aria-hidden="true">i</span>INSIGHT</div>
        <p className="brand-subtitle">AI Insurance Data Agent</p>
        <div className={`agent-status ${health}`} role="status"><span className="status-dot" />{health === 'online' ? 'Agent Online' : health === 'checking' ? 'Connecting to agent…' : 'Agent Offline'}</div>
        <div className="sidebar-resources">
          <section aria-labelledby="database-heading">
            <h2 id="database-heading" className="eyebrow">Database <span>03</span></h2>
            <ul className="database-list">{[['Customers', '500'], ['Policies', '750'], ['Claims', '1,500']].map(([name, count]) => <li key={name}><span>{name}</span><span className="record-count">{count} <small>records</small></span></li>)}</ul>
          </section>
          <section aria-labelledby="knowledge-heading">
            <h2 id="knowledge-heading" className="eyebrow">Knowledge base <span>04</span></h2>
            <ul className="document-list">{documents.map(name => <li key={name}><DocumentIcon /><span>{name}</span></li>)}</ul>
          </section>
        </div>
        <div className="sidebar-footer"><span className="footer-mark" aria-hidden="true">◇</span><div>Built on your data.<br /><span>Grounded in your knowledge.</span></div></div>
      </aside>

      <main>
        <header className="topbar"><span>WORKSPACE <span className="topbar-divider">/</span> <span className="topbar-current">Insurance intelligence</span></span><span className="demo-badge">DEMO ENVIRONMENT</span></header>
        <div className="workspace">
          <div className="intro"><p className="eyebrow intro-label">DATA & KNOWLEDGE, CONNECTED</p><h1>Ask your insurance data.</h1><p className="intro-description">Query structured insurance data and business knowledge using natural language.</p></div>

          <form className="question-form" onSubmit={event => { event.preventDefault(); submitQuestion(question); }}>
            <label htmlFor="question" className="visually-hidden">Your insurance question</label>
            <textarea id="question" rows="3" placeholder="Ask a question about customers, policies, claims or business rules..." value={question} onChange={event => setQuestion(event.target.value)} disabled={loading} onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                submitQuestion(question);
              }
            }} />
            <div className="input-toolbar"><span>Enter to ask <span aria-hidden="true">·</span> Shift + Enter for a new line</span><button className="ask-button" type="submit" disabled={loading || !question.trim()}>ASK <span aria-hidden="true">↗</span></button></div>
          </form>

          <section className="examples" aria-labelledby="examples-heading"><h2 id="examples-heading" className="eyebrow">Try a question</h2><div className="example-grid">{examples.map((example, index) => <button key={example} disabled={loading} onClick={() => submitQuestion(example)}><span className="example-number">0{index + 1}</span><span>{example}</span><span className="example-arrow" aria-hidden="true">↗</span></button>)}</div></section>

          <div aria-live="polite" aria-atomic="true">{loading && <div className="loading-state" role="status"><span className="loading-dot" />Analysing your question...</div>}</div>
          {error && <div className="error-state" role="alert"><strong>Something went wrong</strong><p>{error}</p></div>}
          {result && <section className="response" aria-labelledby="answer-heading" aria-live="polite">
            <div className="response-heading"><h2 id="answer-heading" className="eyebrow"><span className="status-dot" />Answer</h2><span className="response-label">INSIGHT AGENT</span></div>
            <p className="submitted-question">{submittedQuestion}</p>
            <div className="answer-text"><AnswerText text={result.answer} /></div>
            {result.sql !== null && <details className="sql-section" key={submittedQuestion}><summary>SQL USED <span aria-hidden="true">⌄</span></summary><pre><code>{result.sql}</code></pre></details>}
            {result.sources.length > 0 && <div className="sources-section"><h3 className="eyebrow">Sources</h3><ul>{result.sources.map((source, index) => <li key={`${source}-${index}`}><DocumentIcon />{source}</li>)}</ul></div>}
          </section>}
          {!result && !loading && !error && <div className="empty-state"><span aria-hidden="true">⌁</span><p>Your next insight starts with a question.</p><small>Answers backed by your database and policy documents.</small></div>}
          <footer className="workspace-footer">Synthetic insurance data <span aria-hidden="true">·</span> For demonstration purposes</footer>
        </div>
      </main>
    </div>
  );
}
