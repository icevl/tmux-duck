// Display helpers for the agent model shown in the sidebar and composer.
//
// The backend reports what the transcript says: a model id
// ("claude-opus-5-5", "claude-haiku-4-5-20251001", "gpt-5.4") or, right after
// a Claude `/model`, the CLI's display name ("Opus 5.5 (1M context)").

const CLAUDE_ID = /^claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(\[1m\])?$/;
const CLAUDE_DISPLAY = /^(opus|sonnet|haiku|fable)\s+(\d+(?:\.\d+)?)(\s*\(1M context\))?$/i;
const CLAUDE_ALIAS = /^(opus|sonnet|haiku|fable)(\[1m\])?$/;

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

export function formatModel(model: string | null | undefined): string | null {
  if (!model) return null;
  const m = CLAUDE_ID.exec(model);
  if (m) {
    const [, family, major, minor, oneM] = m;
    const version = minor ? `${major}.${minor}` : major;
    return `${capitalize(family)} ${version}${oneM ? " 1M" : ""}`;
  }
  const alias = CLAUDE_ALIAS.exec(model);
  if (alias) return `${capitalize(alias[1])}${alias[2] ? " 1M" : ""}`;
  if (/^gpt-/i.test(model)) return `GPT-${model.slice(4)}`;
  return model.replace(/\s*\(1M context\)/i, " 1M");
}

// "opus-5.5" plus whether the 1M context window is on. `oneM` is null when
// the source cannot tell: Claude stamps replies with the bare id, so a 1M
// session looks like "claude-opus-5-5" in the transcript.
function modelKey(model: string): { key: string; oneM: boolean | null } {
  const id = CLAUDE_ID.exec(model);
  if (id) {
    const [, family, major, minor, oneM] = id;
    return {
      key: `${family}-${minor ? `${major}.${minor}` : major}`,
      oneM: oneM ? true : null,
    };
  }
  const display = CLAUDE_DISPLAY.exec(model);
  if (display) {
    return { key: `${display[1].toLowerCase()}-${display[2]}`, oneM: !!display[3] };
  }
  return { key: model.toLowerCase(), oneM: false };
}

// Does catalog option `optionId` (an explicit id such as
// "claude-opus-5-5[1m]") match the model the session runs? "exact" when the
// version and context window agree; "version" when only the version is
// known (the transcript does not say whether 1M context is on).
export function modelMatch(
  optionId: string,
  current: string | null | undefined,
): "exact" | "version" | null {
  if (!current) return null;
  // A bare Claude id says nothing about the context window, so it is not a
  // sure match even when it equals the option's id.
  if (optionId === current && !CLAUDE_ID.test(current)) return "exact";
  const option = modelKey(optionId);
  const actual = modelKey(current);
  if (option.key !== actual.key) return null;
  if (actual.oneM === null) return "version";
  return (option.oneM ?? false) === actual.oneM ? "exact" : null;
}

export function isCurrentModel(
  optionId: string,
  current: string | null | undefined,
): boolean {
  return modelMatch(optionId, current) !== null;
}
