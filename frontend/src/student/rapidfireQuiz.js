export const RAPIDFIRE_QUIZ_QUESTIONS = [
  {
    question_id: "python-function-keyword",
    question_text: "Which keyword defines a function in Python?",
    question_type: "technical",
    difficulty: "easy",
    options: ["def", "func", "lambda", "method"],
    answer: "def",
    explanation: "Python uses `def` to define a function.",
  },
  {
    question_id: "python-mutable-type",
    question_text: "Which Python type is mutable?",
    question_type: "technical",
    difficulty: "easy",
    options: ["list", "tuple", "string", "integer"],
    answer: "list",
    explanation: "A list can be changed after it is created.",
  },
  {
    question_id: "python-len-result",
    question_text: "What does `len()` return?",
    question_type: "technical",
    difficulty: "easy",
    options: ["length", "index", "value", "type"],
    answer: "length",
    explanation: "`len()` returns the number of items in an object.",
  },
  {
    question_id: "python-no-value",
    question_text: "Which Python value represents no value?",
    question_type: "technical",
    difficulty: "easy",
    options: ["None", "False", "zero", "empty"],
    answer: "None",
    explanation: "`None` is Python's null value.",
  },
  {
    question_id: "sql-read-rows",
    question_text: "Which SQL command reads rows?",
    question_type: "technical",
    difficulty: "easy",
    options: ["SELECT", "UPDATE", "INSERT", "DELETE"],
    answer: "SELECT",
    explanation: "`SELECT` retrieves data from a database.",
  },
  {
    question_id: "http-retrieve-method",
    question_text: "Which HTTP method retrieves data?",
    question_type: "technical",
    difficulty: "easy",
    options: ["GET", "POST", "PUT", "PATCH"],
    answer: "GET",
    explanation: "`GET` requests a resource without changing it.",
  },
  {
    question_id: "http-not-found-status",
    question_text: "Which status code means Not Found?",
    question_type: "technical",
    difficulty: "easy",
    options: ["404", "200", "403", "500"],
    answer: "404",
    explanation: "HTTP 404 means the requested resource was not found.",
  },
  {
    question_id: "html-stylesheet-tag",
    question_text: "Which HTML tag links a stylesheet?",
    question_type: "technical",
    difficulty: "easy",
    options: ["link", "style", "script", "meta"],
    answer: "link",
    explanation: "The `link` tag connects an external stylesheet to a page.",
  },
  {
    question_id: "javascript-constant-keyword",
    question_text: "Which JavaScript keyword declares a constant?",
    question_type: "technical",
    difficulty: "easy",
    options: ["const", "let", "var", "static"],
    answer: "const",
    explanation: "`const` declares a block-scoped binding that cannot be reassigned.",
  },
  {
    question_id: "git-record-changes",
    question_text: "Which Git command records staged changes?",
    question_type: "technical",
    difficulty: "easy",
    options: ["commit", "push", "pull", "clone"],
    answer: "commit",
    explanation: "`git commit` saves staged changes in the local repository history.",
  },
  {
    question_id: "python-unique-collection",
    question_text: "Which Python type stores unique items?",
    question_type: "technical",
    difficulty: "medium",
    options: ["set", "list", "tuple", "string"],
    answer: "set",
    explanation: "A set stores distinct values without duplicates.",
  },
  {
    question_id: "python-exception-keyword",
    question_text: "Which keyword catches an exception?",
    question_type: "technical",
    difficulty: "medium",
    options: ["except", "raise", "assert", "finally"],
    answer: "except",
    explanation: "An `except` block handles an exception raised in its matching `try` block.",
  },
  {
    question_id: "sql-filter-keyword",
    question_text: "Which SQL keyword filters rows?",
    question_type: "technical",
    difficulty: "medium",
    options: ["WHERE", "ORDER", "TABLE", "INDEX"],
    answer: "WHERE",
    explanation: "`WHERE` limits query results to rows matching a condition.",
  },
  {
    question_id: "http-success-status",
    question_text: "Which status code means a request succeeded?",
    question_type: "technical",
    difficulty: "medium",
    options: ["200", "301", "404", "500"],
    answer: "200",
    explanation: "HTTP 200 indicates a successful request.",
  },
  {
    question_id: "javascript-transform-method",
    question_text: "Which JavaScript method transforms each array item?",
    question_type: "technical",
    difficulty: "medium",
    options: ["map", "push", "find", "join"],
    answer: "map",
    explanation: "`map` returns a new array from the result of transforming each item.",
  },
];

export const RAPIDFIRE_QUESTION_COUNT = 5;
export const RAPIDFIRE_DURATION_SECONDS = 150;

export function pickRapidFireQuestions(pool, count = RAPIDFIRE_QUESTION_COUNT) {
  const shuffled = [...pool];
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const swapIndex = Math.floor(Math.random() * (index + 1));
    [shuffled[index], shuffled[swapIndex]] = [shuffled[swapIndex], shuffled[index]];
  }
  return shuffled.slice(0, count);
}
