import { ComponentPropsWithoutRef, memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ChatImage, IMAGE_PATH_RE, imageUrlForPath, isHostPath } from "./ChatImage";

interface Props {
  text: string;
  /** Show image paths (and ![](...) images) as pictures, not links. */
  inlineImages?: boolean;
}

// Codexbot's transcript parser wraps long tool output in sentinel markers
// that map to Telegram's expandable blockquote feature. The STX bytes are
// invisible in the browser but the literal "EXPQUOTE_START/END" text
// survives JSON serialization — translate them into a markdown blockquote
// so the web renders the same intent as the bot.
const EXPQUOTE_BLOCK = /\x02EXPQUOTE_START\x02([\s\S]*?)\x02EXPQUOTE_END\x02/g;
// Defensive fallback: same markers without the STX bytes (e.g. when something
// upstream stripped control chars).
const EXPQUOTE_BLOCK_PLAIN = /EXPQUOTE_START([\s\S]*?)EXPQUOTE_END/g;

// Absolute host paths an agent prints (e.g. "open /Users/me/.agent/x.html").
// Anchored to a known top-level dir + a file extension to avoid linkifying
// arbitrary slash-separated text. A leading `~/` is allowed (backend expands).
const FILE_PATH_RE =
  /(?:~|\/(?:Users|home|root|Volumes|private|tmp|var|opt|mnt|srv|data|etc|usr))\/[^\s'"`)\]<>]+\.[A-Za-z0-9]{1,12}/g;

interface MdastNode {
  type: string;
  value?: string;
  url?: string;
  alt?: string;
  children?: MdastNode[];
}

// Split a text value into text + link nodes wherever a file path appears;
// with `images`, a path to a picture becomes the picture itself.
function splitPathText(value: string, images: boolean): MdastNode[] {
  const out: MdastNode[] = [];
  let last = 0;
  for (const m of value.matchAll(FILE_PATH_RE)) {
    const start = m.index ?? 0;
    if (start > last) out.push({ type: "text", value: value.slice(last, start) });
    const path = m[0];
    if (images && IMAGE_PATH_RE.test(path)) {
      out.push({ type: "image", url: path, alt: path.split("/").pop() });
      last = start + path.length;
      continue;
    }
    out.push({
      type: "link",
      url: `/api/file?path=${encodeURIComponent(path)}`,
      children: [{ type: "text", value: path }],
    });
    last = start + path.length;
  }
  if (out.length === 0) return [{ type: "text", value }];
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

// remark plugin: turn file paths in plain text into download links. Only
// touches `text` nodes, so code blocks / inline code (which carry `value`, not
// child text nodes) and existing links are left untouched.
function remarkLinkifyPaths(options: { images?: boolean } = {}) {
  const walk = (node: MdastNode): void => {
    if (!node.children) return;
    const next: MdastNode[] = [];
    for (const child of node.children) {
      if (child.type === "text" && typeof child.value === "string") {
        next.push(...splitPathText(child.value, !!options.images));
      } else {
        if (child.type !== "link") walk(child);
        next.push(child);
      }
    }
    node.children = next;
  };
  return (tree: MdastNode) => walk(tree);
}

function preprocess(raw: string): string {
  let text = raw;
  const replacer = (_match: string, inner: string) => {
    const lines = inner.trim().split("\n");
    return "\n" + lines.map((l) => `> ${l}`).join("\n") + "\n";
  };
  text = text.replace(EXPQUOTE_BLOCK, replacer);
  text = text.replace(EXPQUOTE_BLOCK_PLAIN, replacer);
  // Strip any remaining stray STX bytes.
  text = text.replace(/\x02/g, "");
  return text;
}

// Split into block-level chunks so unchanged blocks can skip re-parse on edit.
function splitBlocks(text: string): string[] {
  const blocks: string[] = [];
  let buf: string[] = [];
  let inFence = false;
  const flush = () => {
    if (buf.length > 0) {
      blocks.push(buf.join("\n"));
      buf = [];
    }
  };
  for (const line of text.split("\n")) {
    if (line.startsWith("```")) {
      inFence = !inFence;
      buf.push(line);
      continue;
    }
    if (!inFence && line.trim() === "") {
      flush();
      continue;
    }
    buf.push(line);
  }
  flush();
  return blocks;
}

const MD_COMPONENTS = {
  // Outside inline-image mode (tool calls and output), ![alt](src) is text an
  // agent printed — e.g. a command containing Markdown — not a picture.
  img: ({ src, alt }: ComponentPropsWithoutRef<"img">) => (
    <span>{`![${alt ?? ""}](${typeof src === "string" ? src : ""})`}</span>
  ),
  a: ({ href, children, ...rest }: ComponentPropsWithoutRef<"a">) => {
    // File-download links (linkified host paths) download in place rather than
    // opening a blank tab; the backend serves them as attachments.
    if (typeof href === "string" && href.startsWith("/api/file?")) {
      return (
        <a href={href} download {...rest}>
          {children}
        </a>
      );
    }
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
        {children}
      </a>
    );
  },
};

// Plugin lists are module constants so memoised blocks see stable props.
const PLUGINS_LINKS = [remarkGfm, remarkLinkifyPaths];
const PLUGINS_IMAGES: NonNullable<Parameters<typeof ReactMarkdown>[0]["remarkPlugins"]> = [
  remarkGfm,
  [remarkLinkifyPaths, { images: true }],
];

const MD_COMPONENTS_IMAGES = {
  ...MD_COMPONENTS,
  img: ({ src, alt }: ComponentPropsWithoutRef<"img">) => {
    if (typeof src !== "string" || !src) return null;
    // An agent's ![caption](/abs/path.png) or a bare screenshot path: load it
    // through the authenticated image endpoint.
    return <ChatImage src={isHostPath(src) ? imageUrlForPath(src) : src} alt={alt} />;
  },
};

const MarkdownBlock = memo(function MarkdownBlock({
  text,
  inlineImages,
}: {
  text: string;
  inlineImages: boolean;
}) {
  return (
    <ReactMarkdown
      remarkPlugins={inlineImages ? PLUGINS_IMAGES : PLUGINS_LINKS}
      components={inlineImages ? MD_COMPONENTS_IMAGES : MD_COMPONENTS}
    >
      {text}
    </ReactMarkdown>
  );
});

export const Markdown = memo(function Markdown({ text, inlineImages = false }: Props) {
  const blocks = useMemo(() => splitBlocks(preprocess(text)), [text]);
  return (
    <div className="md">
      {blocks.map((b, i) => (
        <MarkdownBlock key={i} text={b} inlineImages={inlineImages} />
      ))}
    </div>
  );
});
