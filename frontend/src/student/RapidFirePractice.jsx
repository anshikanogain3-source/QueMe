import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  CheckCircle2,
  RotateCcw,
  Timer,
  XCircle,
} from "lucide-react";
import { StudentWorkspace } from "./StudentWorkspace.jsx";
import {
  pickRapidFireQuestions,
  RAPIDFIRE_DURATION_SECONDS,
  RAPIDFIRE_QUIZ_QUESTIONS,
} from "./rapidfireQuiz.js";

export function RapidFirePractice({ user }) {
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [selectedDifficulty, setSelectedDifficulty] = useState("all");
  const [roundQuestions, setRoundQuestions] = useState(() =>
    pickRapidFireQuestions(RAPIDFIRE_QUIZ_QUESTIONS)
  );
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [timeLeft, setTimeLeft] = useState(RAPIDFIRE_DURATION_SECONDS);
  const [finished, setFinished] = useState(false);

  const questionPool = useMemo(
    () => RAPIDFIRE_QUIZ_QUESTIONS.filter((question) => {
      const matchesCategory = selectedCategory === "all" ||
        question.question_type === selectedCategory;
      const matchesDifficulty = selectedDifficulty === "all" ||
        question.difficulty === selectedDifficulty;
      return matchesCategory && matchesDifficulty;
    }),
    [selectedCategory, selectedDifficulty]
  );

  const activeQuestion = roundQuestions[currentIndex];
  const selectedAnswer = activeQuestion ? answers[activeQuestion.question_id] : undefined;
  const score = roundQuestions.filter(
    (question) => answers[question.question_id] === question.answer
  ).length;
  const answeredCount = Object.keys(answers).length;

  useEffect(() => {
    if (finished) return undefined;
    const timer = window.setInterval(() => {
      setTimeLeft((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [finished]);

  useEffect(() => {
    if (timeLeft === 0) setFinished(true);
  }, [timeLeft]);

  function startRound(pool = questionPool) {
    setRoundQuestions(pickRapidFireQuestions(pool));
    setCurrentIndex(0);
    setAnswers({});
    setTimeLeft(RAPIDFIRE_DURATION_SECONDS);
    setFinished(false);
  }

  function changeCategory(category) {
    setSelectedCategory(category);
    const pool = RAPIDFIRE_QUIZ_QUESTIONS.filter((question) =>
      (category === "all" || question.question_type === category) &&
      (selectedDifficulty === "all" || question.difficulty === selectedDifficulty)
    );
    startRound(pool);
  }

  function changeDifficulty(difficulty) {
    setSelectedDifficulty(difficulty);
    const pool = RAPIDFIRE_QUIZ_QUESTIONS.filter((question) =>
      (selectedCategory === "all" || question.question_type === selectedCategory) &&
      (difficulty === "all" || question.difficulty === difficulty)
    );
    startRound(pool);
  }

  function chooseAnswer(option) {
    if (selectedAnswer !== undefined || !activeQuestion) return;
    setAnswers((previous) => ({ ...previous, [activeQuestion.question_id]: option }));
  }

  function advanceQuestion() {
    if (currentIndex === roundQuestions.length - 1) setFinished(true);
    else setCurrentIndex((index) => index + 1);
  }

  const formatTime = `${Math.floor(timeLeft / 60)}:${String(timeLeft % 60).padStart(2, "0")}`;

  return (
    <StudentWorkspace
      user={user}
      active="rapidfire"
      pageTitle="RapidFire"
      pageSubtitle="2½ minute quiz"
    >
      <div className="rapidfire-container">
        <section className="rapidfire-intro-card">
          <div className="intro-copy">
            <span className="eyebrow eyebrow-blue">SPONTANEOUS REASONING</span>
            <h2>RapidFire Mini Quiz</h2>
            <p>
              Five quick multiple-choice questions. Pick the one-word answer and see instant
              feedback. Your practice results stay in this session and are not stored permanently.
            </p>
          </div>

          <div className="rapidfire-filter-row">
            <div className="filter-group">
              <span className="filter-group-label">Category:</span>
              {["all", "technical"].map((category) => (
                <button
                  key={category}
                  type="button"
                  className={`filter-pill-btn${selectedCategory === category ? " active" : ""}`}
                  onClick={() => changeCategory(category)}
                >
                  {category === "all" ? `All (${questionPool.length})` : "Technical"}
                </button>
              ))}
            </div>

            <div className="filter-group">
              <span className="filter-group-label">Difficulty:</span>
              {["all", "easy", "medium"].map((difficulty) => (
                <button
                  key={difficulty}
                  type="button"
                  className={`filter-pill-btn${selectedDifficulty === difficulty ? " active" : ""}`}
                  onClick={() => changeDifficulty(difficulty)}
                >
                  {difficulty.charAt(0).toUpperCase() + difficulty.slice(1)}
                </button>
              ))}
            </div>
          </div>
        </section>

        {finished ? (
          <section className="rapidfire-card completion-card">
            <div className="completion-mark">
              <CheckCircle2 size={36} />
            </div>
            <span className="eyebrow eyebrow-blue">
              {timeLeft === 0 ? "TIME'S UP" : "ROUND COMPLETED"}
            </span>
            <h2>Quick round complete</h2>
            <p>
              You got <strong>{score} of {roundQuestions.length}</strong> correct and answered{" "}
              <strong>{answeredCount} of {roundQuestions.length}</strong> questions.
            </p>
            <div className="completion-actions">
              <button type="button" className="button button-outline" onClick={() => startRound()}>
                <RotateCcw size={15} />
                <span>Play another round</span>
              </button>
              <Link to="/practice-interviews" className="button button-primary">
                <span>Go to Mock Interviews</span>
                <ArrowRight size={15} />
              </Link>
            </div>
          </section>
        ) : (
          <section className="rapidfire-card active-question-card">
            <div className="card-header">
              <div className="progress-info">
                <span className="question-counter">
                  Question <strong>{currentIndex + 1}</strong> of <strong>{roundQuestions.length}</strong>
                </span>
                <div className="rapidfire-question-meta">
                  <span className="status-pill status-in_progress">Technical</span>
                  <span className="status-pill status-scheduled">
                    {activeQuestion?.difficulty || "Easy"}
                  </span>
                  <span className={`rapidfire-timer${timeLeft <= 30 ? " is-low" : ""}`}>
                    <Timer size={14} aria-hidden="true" />
                    <span aria-live="polite">{formatTime}</span>
                  </span>
                </div>
              </div>

              <div
                className="progress-meter"
                role="progressbar"
                aria-label="Quiz progress"
                aria-valuenow={currentIndex + 1}
                aria-valuemin={1}
                aria-valuemax={roundQuestions.length}
              >
                <span style={{ width: `${((currentIndex + 1) / roundQuestions.length) * 100}%` }} />
              </div>
            </div>

            <div className="question-content rapidfire-quiz-content">
              <h3 className="prompt-text">{activeQuestion?.question_text}</h3>
              <div className="rapidfire-answer-grid" role="group" aria-label="Choose one answer">
                {activeQuestion?.options.map((option) => {
                  const isSelected = selectedAnswer === option;
                  const isCorrect = option === activeQuestion.answer;
                  const resultClass = selectedAnswer === undefined
                    ? ""
                    : isCorrect ? " is-correct" : isSelected ? " is-incorrect" : "";
                  return (
                    <button
                      key={option}
                      type="button"
                      className={`rapidfire-answer-option${resultClass}`}
                      aria-pressed={isSelected}
                      disabled={selectedAnswer !== undefined}
                      onClick={() => chooseAnswer(option)}
                    >
                      {option}
                    </button>
                  );
                })}
              </div>

              {selectedAnswer !== undefined && (
                <div className={`rapidfire-answer-feedback${selectedAnswer === activeQuestion.answer ? " is-correct" : " is-incorrect"}`} role="status">
                  {selectedAnswer === activeQuestion.answer
                    ? <CheckCircle2 size={17} aria-hidden="true" />
                    : <XCircle size={17} aria-hidden="true" />}
                  <span>
                    <strong>{selectedAnswer === activeQuestion.answer ? "Correct!" : `Answer: ${activeQuestion.answer}.`}</strong>{" "}
                    {activeQuestion.explanation}
                  </span>
                </div>
              )}
            </div>

            <div className="question-footer">
              <div className="footer-left">
                <button type="button" className="button button-quiet button-small" onClick={() => startRound()}>
                  <RotateCcw size={14} />
                  <span>Restart</span>
                </button>
              </div>
              <div className="footer-right">
                <button
                  type="button"
                  className="button button-primary"
                  disabled={selectedAnswer === undefined}
                  onClick={advanceQuestion}
                >
                  <span>{currentIndex === roundQuestions.length - 1 ? "Finish Quiz" : "Next Question"}</span>
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
