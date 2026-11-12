import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronRight,
  Layers,
  RotateCcw,
  Sparkles,
  Zap,
} from "lucide-react";
import { api } from "../api.js";
import { StudentWorkspace } from "./StudentWorkspace.jsx";

export function RapidFirePractice({ user }) {
  const [allQuestions, setAllQuestions] = useState(null);
  const [error, setError] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedDifficulty, setSelectedDifficulty] = useState("all");
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [finished, setFinished] = useState(false);

  useEffect(() => {
    let active = true;
    api("/rapidfire/questions")
      .then((data) => {
        if (active) setAllQuestions(data || []);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, []);

  // Filter questions based on category and difficulty
  const questions = useMemo(() => {
    if (!allQuestions) return [];
    return allQuestions.filter((q) => {
      const matchCat =
        selectedCategory === "all" ||
        (q.question_type &&
          q.question_type.toLowerCase() === selectedCategory.toLowerCase());
      const matchDiff =
        selectedDifficulty === "all" ||
        (q.difficulty &&
          q.difficulty.toLowerCase() === selectedDifficulty.toLowerCase());
      return matchCat && matchDiff;
    });
  }, [allQuestions, selectedCategory, selectedDifficulty]);

  // Categories available from questions
  const categories = useMemo(() => {
    if (!allQuestions) return [];
    const set = new Set();
    allQuestions.forEach((q) => {
      if (q.question_type) set.add(q.question_type.toLowerCase());
    });
    return Array.from(set);
  }, [allQuestions]);

  const activeQuestion = questions[currentIndex];
  const answeredCount = Object.values(answers).filter(
    (ans) => typeof ans === "string" && ans.trim().length > 0
  ).length;

  function resetSession() {
    setAnswers({});
    setCurrentIndex(0);
    setFinished(false);
  }

  function handleCategoryChange(cat) {
    setSelectedCategory(cat);
    setCurrentIndex(0);
    setAnswers({});
    setFinished(false);
  }

  function handleDifficultyChange(diff) {
    setSelectedDifficulty(diff);
    setCurrentIndex(0);
    setAnswers({});
    setFinished(false);
  }

  return (
    <StudentWorkspace
      user={user}
      active="rapidfire"
      pageTitle="RapidFire"
      pageSubtitle="Speed Practice"
    >
      <div className="rapidfire-container">
        {error && (
          <div className="alert alert-error" role="alert">
            {error}
          </div>
        )}

        {/* Top Info Banner */}
        <section className="rapidfire-intro-card">
          <div className="intro-copy">
            <span className="eyebrow eyebrow-blue">SPONTANEOUS REASONING</span>
            <h2>RapidFire Question Practice</h2>
            <p>
              Answer short, focused prompts to build quick thinking, articulation, and confidence.
              Responses stay in this session and are not graded or saved permanently.
            </p>
          </div>

          <div className="rapidfire-filter-row">
            <div className="filter-group">
              <span className="filter-group-label">Category:</span>
              <button
                type="button"
                className={`filter-pill-btn${selectedCategory === "all" ? " active" : ""}`}
                onClick={() => handleCategoryChange("all")}
              >
                All ({allQuestions?.length || 0})
              </button>
              {categories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  className={`filter-pill-btn${selectedCategory === cat ? " active" : ""}`}
                  onClick={() => handleCategoryChange(cat)}
                >
                  {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </button>
              ))}
            </div>

            <div className="filter-group">
              <span className="filter-group-label">Difficulty:</span>
              {["all", "easy", "medium", "hard"].map((diff) => (
                <button
                  key={diff}
                  type="button"
                  className={`filter-pill-btn${selectedDifficulty === diff ? " active" : ""}`}
                  onClick={() => handleDifficultyChange(diff)}
                >
                  {diff.charAt(0).toUpperCase() + diff.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </section>

        {/* Question Practice Interface */}
        {allQuestions === null ? (
          <div className="loading-container">
            <span className="spinner" />
            <span>Finding practice questions…</span>
          </div>
        ) : questions.length === 0 ? (
          <div className="empty-state">
            <div className="empty-mark">
              <Activity size={24} />
            </div>
            <h3>No questions available in this filter</h3>
            <p>
              {allQuestions.length === 0
                ? "RapidFire uses questions from interviews assigned by your teacher. Once assigned, you can practice them here."
                : "No questions match the selected category and difficulty. Try selecting 'All'."}
            </p>
            {allQuestions.length > 0 && (
              <button
                type="button"
                className="button button-outline button-small"
                onClick={() => {
                  setSelectedCategory("all");
                  setSelectedDifficulty("all");
                }}
              >
                Reset Filters
              </button>
            )}
          </div>
        ) : finished ? (
          /* Finished State */
          <section className="rapidfire-card completion-card">
            <div className="completion-mark">
              <CheckCircle2 size={36} />
            </div>
            <span className="eyebrow eyebrow-blue">ROUND COMPLETED</span>
            <h2>Great Practice Session!</h2>
            <p>
              You completed questions in this round and responded to{" "}
              <strong>
                {answeredCount} of {questions.length}
              </strong>{" "}
              prompts.
            </p>

            <div className="completion-actions">
              <button
                type="button"
                className="button button-outline"
                onClick={resetSession}
              >
                <RotateCcw size={15} />
                <span>Practice Another Round</span>
              </button>
              <Link to="/practice-interviews" className="button button-primary">
                <span>Go to Mock Interviews</span>
                <ArrowRight size={15} />
              </Link>
            </div>
          </section>
        ) : (
          /* Active Question Card */
          <section className="rapidfire-card active-question-card">
            <div className="card-header">
              <div className="progress-info">
                <span className="question-counter">
                  Question <strong>{currentIndex + 1}</strong> of{" "}
                  <strong>{questions.length}</strong>
                </span>
                <div className="question-badges">
                  <span className="status-pill status-in_progress">
                    {activeQuestion?.question_type || "General"}
                  </span>
                  <span className="status-pill status-scheduled">
                    {activeQuestion?.difficulty || "Medium"}
                  </span>
                </div>
              </div>

              {/* Linear Progress Bar */}
              <div
                className="progress-meter"
                role="progressbar"
                aria-valuenow={currentIndex + 1}
                aria-valuemin={1}
                aria-valuemax={questions.length}
              >
                <span
                  style={{
                    width: `${((currentIndex + 1) / questions.length) * 100}%`,
                  }}
                />
              </div>
            </div>

            <div className="question-content">
              <h3 className="prompt-text">{activeQuestion?.question_text}</h3>

              <div className="response-box">
                <div className="response-header">
                  <label htmlFor="rapidfire-textarea">
                    Draft your thoughts or key points
                  </label>
                  <span className="optional-tag">Optional practice notes</span>
                </div>
                <textarea
                  id="rapidfire-textarea"
                  rows={5}
                  value={answers[activeQuestion?.question_id] || ""}
                  onChange={(e) =>
                    setAnswers((prev) => ({
                      ...prev,
                      [activeQuestion.question_id]: e.target.value,
                    }))
                  }
                  placeholder="Bullet down your key talking points or outline how you would articulate this answer aloud…"
                  maxLength={3000}
                />
              </div>
            </div>

            <div className="question-footer">
              <div className="footer-left">
                {currentIndex > 0 && (
                  <button
                    type="button"
                    className="button button-outline button-small"
                    onClick={() => setCurrentIndex((prev) => prev - 1)}
                  >
                    <ArrowLeft size={14} />
                    <span>Previous</span>
                  </button>
                )}
                <button
                  type="button"
                  className="button button-quiet button-small"
                  onClick={resetSession}
                >
                  <RotateCcw size={14} />
                  <span>Restart</span>
                </button>
              </div>

              <div className="footer-right">
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() => {
                    if (currentIndex === questions.length - 1) {
                      setFinished(true);
                    } else {
                      setCurrentIndex((prev) => prev + 1);
                    }
                  }}
                >
                  <span>
                    {currentIndex === questions.length - 1
                      ? "Finish Round"
                      : "Next Question"}
                  </span>
                  <ArrowRight size={15} />
                </button>
              </div>
            </div>
          </section>
        )}
      </div>
    </StudentWorkspace>
  );
}

