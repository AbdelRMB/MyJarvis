import { Check, Copy } from "lucide-react";
import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

function BlocCode({ code, langue }: { code: string; langue: string }) {
  const [copie, setCopie] = useState(false);
  return (
    <div className="group overflow-hidden rounded-md border border-ligne bg-black/40">
      <div className="flex items-center justify-between border-b border-ligne bg-white/[0.02] px-3 py-1.5">
        <span className="font-mono text-[11px] text-doux">{langue || "code"}</span>
        <button
          onClick={() => {
            navigator.clipboard.writeText(code);
            setCopie(true);
            setTimeout(() => setCopie(false), 1500);
          }}
          className="flex items-center gap-1 text-[11px] text-doux hover:text-hud"
        >
          {copie ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          {copie ? "Copié" : "Copier"}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 font-mono text-[13px] leading-relaxed text-hud-clair">
        <code>{code}</code>
      </pre>
    </div>
  );
}

export const Markdown = memo(function Markdown({ texte }: { texte: string }) {
  return (
    <div className="prose-wesley">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          pre: ({ children }) => <>{children}</>,
          code: ({ className, children }) => {
            const contenu = String(children ?? "");
            const langue = /language-(\w+)/.exec(className ?? "")?.[1];
            if (langue || contenu.includes("\n")) return <BlocCode code={contenu.replace(/\n$/, "")} langue={langue ?? ""} />;
            return <code>{children}</code>;
          },
        }}
      >
        {texte}
      </ReactMarkdown>
    </div>
  );
});
