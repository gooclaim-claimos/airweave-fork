import React, { useState, useMemo, useCallback } from 'react';
import { API_CONFIG } from '@/lib/api';
import { Terminal, Copy, Check, ExternalLink, X } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useTheme } from '@/lib/theme-provider';
import { cn } from '@/lib/utils';
import { PythonIcon } from '@/components/icons/PythonIcon';
import { NodeIcon } from '@/components/icons/NodeIcon';
import { McpIcon } from '@/components/icons/McpIcon';

// Local type aliases — avoids circular import with SearchBox
type SearchTier = "instant" | "classic" | "agentic";
type RetrievalStrategy = "hybrid" | "neural" | "keyword";

type ApiTab = "rest" | "python" | "node" | "mcp";

const TABS: { id: ApiTab; label: string; icon: React.FC<{ className?: string }> }[] = [
    { id: "rest", label: "cURL", icon: Terminal },
    { id: "python", label: "Python", icon: PythonIcon },
    { id: "node", label: "Node.js", icon: NodeIcon },
    { id: "mcp", label: "MCP", icon: McpIcon },
];

interface ApiIntegrationDocProps {
    collectionReadableId: string;
    query?: string;
    tier: SearchTier;
    retrievalStrategy?: RetrievalStrategy;
    thinking?: boolean;
    filter?: any[];
    apiKey?: string;
    onClose?: () => void;
}

export const ApiIntegrationDoc = ({
    collectionReadableId,
    query,
    tier,
    retrievalStrategy = "hybrid",
    thinking = false,
    filter = [],
    apiKey = "YOUR_API_KEY",
    onClose,
}: ApiIntegrationDocProps) => {
    const [apiTab, setApiTab] = useState<ApiTab>("rest");
    const [copied, setCopied] = useState(false);

    const { resolvedTheme } = useTheme();
    const isDark = resolvedTheme === 'dark';

    const handleCopy = useCallback(async (text: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (error) {
            console.error('Failed to copy:', error);
        }
    }, []);

    const endpoints = useMemo(() => {
        const apiBaseUrl = API_CONFIG.baseURL;
        const searchQuery = query || "Ask a question about your data";
        const hasFilters = filter.length > 0;

        const escapeForJson = (str: string) => str.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
        const escapeForPython = (str: string) => str.replace(/\\/g, '\\\\').replace(/"/g, '\\"');

        const apiUrl = `${apiBaseUrl}/collections/${collectionReadableId}/search/${tier}`;

        // Request body per tier
        let requestBody: any;
        switch (tier) {
            case "instant":
                requestBody = {
                    query: searchQuery,
                    retrieval_strategy: retrievalStrategy,
                    ...(hasFilters && { filter }),
                };
                break;
            case "classic":
                requestBody = {
                    query: searchQuery,
                    ...(hasFilters && { filter }),
                };
                break;
            case "agentic":
                requestBody = {
                    query: searchQuery,
                    thinking,
                    ...(hasFilters && { filter }),
                };
                break;
        }

        const jsonBody = JSON.stringify(requestBody, null, 2)
            .split('\n')
            .map((line, index, array) => {
                if (index === 0) return line;
                if (index === array.length - 1) return '  ' + line;
                return '  ' + line;
            })
            .join('\n');

        // ─── cURL
        const curlSnippet = `curl -X 'POST' \\
  '${apiUrl}' \\
  -H 'accept: application/json' \\
  -H 'x-api-key: ${apiKey}' \\
  -H 'Content-Type: application/json' \\
  -d '${jsonBody}'`;

        // ─── Python
        const sdkMethodPython = tier === "instant" ? "search_instant"
            : tier === "classic" ? "search_classic"
            : "search_agentic";

        const pythonParams: string[] = [
            `        "query": "${escapeForPython(searchQuery)}"`,
        ];
        if (tier === "instant") {
            pythonParams.push(`        "retrieval_strategy": "${retrievalStrategy}"`);
        }
        if (tier === "agentic") {
            pythonParams.push(`        "thinking": ${thinking ? "True" : "False"}`);
        }
        if (hasFilters) {
            pythonParams.push(`        "filter": ${JSON.stringify(filter, null, 4)
                .split('\n')
                .map((l, i) => i === 0 ? l : '        ' + l)
                .join('\n')}`);
        }

        const pythonSnippet =
            `from airweave import AirweaveSDK

client = AirweaveSDK(
    api_key="${apiKey}",
)

response = client.collections.${sdkMethodPython}(
    readable_id="${collectionReadableId}",
    request={
${pythonParams.join(',\n')},
    },
)
print(response.results${tier === "agentic" ? ", response.answer" : ""})`;

        // ─── Node.js
        const sdkMethodNode = tier === "instant" ? "searchInstant"
            : tier === "classic" ? "searchClassic"
            : "searchAgentic";

        const nodeParams: string[] = [
            `            query: "${escapeForJson(searchQuery)}"`,
        ];
        if (tier === "instant") {
            nodeParams.push(`            retrievalStrategy: "${retrievalStrategy}"`);
        }
        if (tier === "agentic") {
            nodeParams.push(`            thinking: ${thinking}`);
        }
        if (hasFilters) {
            nodeParams.push(`            filter: ${JSON.stringify(filter, null, 4)
                .split('\n')
                .map((l, i) => i === 0 ? l : '            ' + l)
                .join('\n')}`);
        }

        const nodeSnippet =
            `import { AirweaveSDKClient } from "@airweave/sdk";

const client = new AirweaveSDKClient({ apiKey: "${apiKey}" });

const response = await client.collections.${sdkMethodNode}(
    "${collectionReadableId}",
    {
        request: {
${nodeParams.join(',\n')},
        }
    }
);

console.log(response.results${tier === "agentic" ? ", response.answer" : ""});`;

        // ─── MCP config
        const configSnippet = `// Add to your MCP client config
// e.g. ~/.config/Claude/claude_desktop_config.json

{
  "mcpServers": {
    "airweave-${collectionReadableId}": {
      "command": "npx",
      "args": ["airweave-mcp-search"],
      "env": {
        "AIRWEAVE_API_KEY": "${apiKey}",
        "AIRWEAVE_COLLECTION": "${collectionReadableId}",
        "AIRWEAVE_BASE_URL": "${apiBaseUrl}"
      }
    }
  }
}`;

        return { curlSnippet, pythonSnippet, nodeSnippet, configSnippet, apiUrl };
    }, [collectionReadableId, apiKey, tier, retrievalStrategy, thinking, filter, query]);

    const currentCode = apiTab === "rest" ? endpoints.curlSnippet
        : apiTab === "python" ? endpoints.pythonSnippet
        : apiTab === "node" ? endpoints.nodeSnippet
        : endpoints.configSnippet;

    const currentLanguage = apiTab === "rest" ? "bash"
        : apiTab === "python" ? "python"
        : apiTab === "node" ? "javascript"
        : "javascript"; // jsonc — JS highlights // comments in the MCP config

    const syntaxStyle = isDark ? oneDark : oneLight;

    const linkColor = isDark
        ? 'text-blue-400 hover:text-blue-300'
        : 'text-blue-600 hover:text-blue-500';

    return (
        <div className={cn(
            "w-full font-mono rounded-lg overflow-hidden border",
            isDark ? "bg-gray-950 border-gray-800" : "bg-white border-gray-200"
        )}>
            {/* ── Tab bar with copy + close ── */}
            <div className={cn(
                "flex items-center px-3 border-b",
                isDark ? "border-gray-800" : "border-gray-200"
            )}>
                <div className="flex items-center gap-0 flex-1">
                {TABS.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = apiTab === tab.id;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setApiTab(tab.id)}
                            className={cn(
                                "flex items-center gap-1.5 px-3 py-2 text-[11px] transition-colors relative",
                                isActive
                                    ? isDark ? "text-gray-200" : "text-gray-800"
                                    : isDark ? "text-gray-500 hover:text-gray-300" : "text-gray-400 hover:text-gray-600"
                            )}
                        >
                            <Icon className="h-3.5 w-3.5" />
                            {tab.label}
                            {isActive && (
                                <div className={cn(
                                    "absolute bottom-0 left-0 right-0 h-0.5",
                                    isDark ? "bg-blue-400" : "bg-blue-600"
                                )} />
                            )}
                        </button>
                    );
                })}
                </div>
                <div className="flex items-center gap-3">
                    <button
                        onClick={() => handleCopy(currentCode)}
                        className={cn(
                            "inline-flex items-center gap-1 text-[10px] transition-colors",
                            isDark ? "text-gray-600 hover:text-gray-400" : "text-gray-400 hover:text-gray-600"
                        )}
                    >
                        {copied
                            ? <><Check className="h-3 w-3" /> copied</>
                            : <><Copy className="h-3 w-3" /> copy</>
                        }
                    </button>
                    {onClose && (
                        <button
                            onClick={onClose}
                            className={cn(
                                "inline-flex items-center justify-center h-5 w-5 rounded transition-colors",
                                isDark ? "text-gray-600 hover:text-gray-300 hover:bg-gray-800" : "text-gray-400 hover:text-gray-700 hover:bg-gray-200"
                            )}
                            title="Close (Esc)"
                        >
                            <X className="h-3.5 w-3.5" />
                        </button>
                    )}
                </div>
            </div>

            {/* ── Code content ── */}
            <div className={cn(
                "overflow-auto h-[360px] raw-data-scrollbar",
                isDark ? "bg-gray-950" : "bg-gray-50"
            )}>
                <SyntaxHighlighter
                    language={currentLanguage}
                    style={syntaxStyle}
                    customStyle={{
                        margin: 0,
                        padding: '0.75rem',
                        background: 'transparent',
                        backgroundColor: 'transparent',
                        fontSize: '11px',
                        lineHeight: '1.6',
                    }}
                    codeTagProps={{ style: { background: 'transparent', backgroundColor: 'transparent' } }}
                    showLineNumbers={false}
                    wrapLongLines={false}
                >
                    {currentCode}
                </SyntaxHighlighter>
            </div>

            {/* ── Footer ── */}
            <div className={cn(
                "flex items-center gap-2 px-3 py-2 border-t text-[10px]",
                isDark ? "border-gray-800" : "border-gray-200"
            )}>
                <a
                    href="https://docs.gooclaim.com"
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn("inline-flex items-center gap-1 transition-colors", linkColor)}
                >
                    <ExternalLink className="h-3 w-3" />
                    API documentation
                </a>
            </div>
        </div>
    );
};
