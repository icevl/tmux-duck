import { useMemo } from "react";
import CodeMirror, { EditorView, type Extension } from "@uiw/react-codemirror";
import { oneDark } from "@codemirror/theme-one-dark";
import { javascript } from "@codemirror/lang-javascript";
import { python } from "@codemirror/lang-python";
import { json } from "@codemirror/lang-json";
import { yaml } from "@codemirror/lang-yaml";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { markdown } from "@codemirror/lang-markdown";
import { sql } from "@codemirror/lang-sql";
import { rust } from "@codemirror/lang-rust";
import { go } from "@codemirror/lang-go";

interface Props {
  text: string;
  path: string;
  editable?: boolean;
  onChange?: (value: string) => void;
}

function languageExtensionFor(path: string): Extension | null {
  const dot = path.lastIndexOf(".");
  if (dot < 0) return null;
  const ext = path.slice(dot + 1).toLowerCase();
  switch (ext) {
    case "ts":
    case "tsx":
      return javascript({ jsx: true, typescript: true });
    case "js":
    case "jsx":
    case "mjs":
    case "cjs":
      return javascript({ jsx: ext === "jsx" });
    case "py":
      return python();
    case "json":
      return json();
    case "yml":
    case "yaml":
      return yaml();
    case "html":
    case "htm":
      return html();
    case "css":
    case "scss":
      return css();
    case "md":
    case "markdown":
    case "mdx":
      return markdown();
    case "sql":
      return sql();
    case "rs":
      return rust();
    case "go":
      return go();
    default:
      return null;
  }
}

export function CodeViewer({ text, path, editable = false, onChange }: Props) {
  const extensions = useMemo<Extension[]>(() => {
    const exts: Extension[] = [
      EditorView.lineWrapping,
      EditorView.editable.of(editable),
    ];
    const lang = languageExtensionFor(path);
    if (lang) exts.push(lang);
    return exts;
  }, [path, editable]);

  return (
    <CodeMirror
      value={text}
      extensions={extensions}
      theme={oneDark}
      readOnly={!editable}
      onChange={onChange}
      basicSetup={{
        lineNumbers: true,
        foldGutter: true,
        highlightActiveLine: editable,
        highlightActiveLineGutter: editable,
        autocompletion: editable,
        searchKeymap: true,
      }}
      className="code-viewer"
    />
  );
}
