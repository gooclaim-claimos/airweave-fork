import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plug, Plus, Copy, Mail, Check, Sparkles } from "lucide-react";
import { useTheme } from "@/lib/theme-provider";
import { cn } from "@/lib/utils";
import { IS_GOOCLAIM_TENANT } from "@/config/env";
import { toast } from "sonner";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";

interface RequestConnectorButtonProps {
    onClick?: () => void;
}

const SUPPORT_EMAIL = IS_GOOCLAIM_TENANT
    ? "support@gooclaim.com"
    : "support@airweave.ai";

const POPULAR_REQUESTS = [
    "Zoho CRM",
    "BambooHR",
    "Freshdesk",
    "Internal SQL warehouse",
    "Microsoft Teams",
];

const buildEmailBody = (
    connectorName: string,
    useCase: string,
    requesterEmail: string,
) => {
    const lines = [
        `Connector / App:  ${connectorName || "(not specified)"}`,
        "",
        "Use case:",
        useCase || "(not specified)",
        "",
        `Requested by:     ${requesterEmail || "(not specified)"}`,
    ];
    return lines.join("\n");
};

export const RequestConnectorButton = ({ onClick }: RequestConnectorButtonProps) => {
    const { resolvedTheme } = useTheme();
    const isDark = resolvedTheme === "dark";

    const [open, setOpen] = useState(false);
    const [connectorName, setConnectorName] = useState("");
    const [useCase, setUseCase] = useState("");
    const [requesterEmail, setRequesterEmail] = useState("");
    const [justCopied, setJustCopied] = useState(false);

    const resetForm = () => {
        setConnectorName("");
        setUseCase("");
        setRequesterEmail("");
        setJustCopied(false);
    };

    const handleOpenChange = (next: boolean) => {
        if (!next) resetForm();
        setOpen(next);
    };

    const handleCardClick = () => {
        if (onClick) {
            onClick();
            return;
        }
        setOpen(true);
    };

    const formIsEmpty = !connectorName.trim() && !useCase.trim();

    const handleCopy = async () => {
        const body = buildEmailBody(connectorName.trim(), useCase.trim(), requesterEmail.trim());
        const payload = `To:      ${SUPPORT_EMAIL}\nSubject: Connector Request — ${connectorName.trim() || "untitled"}\n\n${body}`;
        try {
            await navigator.clipboard.writeText(payload);
            setJustCopied(true);
            toast.success("Request copied to clipboard");
            window.setTimeout(() => setJustCopied(false), 1800);
        } catch {
            toast.error("Could not access clipboard");
        }
    };

    const handleSendViaEmail = () => {
        const subject = encodeURIComponent(
            `Connector Request — ${connectorName.trim() || "untitled"}`,
        );
        const body = encodeURIComponent(
            buildEmailBody(connectorName.trim(), useCase.trim(), requesterEmail.trim()),
        );
        // location.href, NOT window.open(..., '_blank'). The latter opens
        // a fresh tab that stays blank when no system mailto handler is
        // configured — the original bug this modal replaces.
        window.location.href = `mailto:${SUPPORT_EMAIL}?subject=${subject}&body=${body}`;
    };

    return (
        <>
            <TooltipProvider delayDuration={100}>
                <Tooltip>
                    <TooltipTrigger asChild>
                        <div
                            className={cn(
                                "border rounded-lg overflow-hidden group transition-all min-w-[150px] cursor-pointer opacity-60 hover:opacity-80",
                                isDark
                                    ? "border-gray-800 hover:border-gray-700 bg-gray-900/30 hover:bg-gray-900/50"
                                    : "border-gray-300 hover:border-gray-300 bg-gray-50 hover:bg-gray-100",
                            )}
                            onClick={handleCardClick}
                        >
                            <div className="p-2 sm:p-3 md:p-4 flex items-center justify-between">
                                <div className="flex items-center gap-2 sm:gap-3">
                                    <div
                                        className={cn(
                                            "flex items-center justify-center w-8 h-8 sm:w-9 sm:h-9 md:w-10 md:h-10 rounded-md flex-shrink-0",
                                            isDark ? "bg-gray-600" : "bg-gray-300",
                                        )}
                                    >
                                        <Plug className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 text-white opacity-90" />
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="text-xs sm:text-sm font-medium text-muted-foreground">
                                            Can't Find Your App?
                                        </span>
                                        <span className="text-xs text-muted-foreground/70 mt-0.5">
                                            Tell us what you need
                                        </span>
                                    </div>
                                </div>
                                <Button
                                    size="icon"
                                    variant="ghost"
                                    className={cn(
                                        "h-6 w-6 sm:h-7 sm:w-7 md:h-8 md:w-8 rounded-full flex-shrink-0",
                                        isDark
                                            ? "bg-gray-800/80 text-gray-400 hover:bg-gray-700/50 hover:text-gray-300 group-hover:bg-gray-700/80"
                                            : "bg-gray-100/80 text-gray-600 hover:bg-gray-200/80 hover:text-gray-700 group-hover:bg-gray-200/80",
                                    )}
                                >
                                    <Plus className="h-3 w-3 sm:h-3.5 sm:w-3.5 md:h-4 md:w-4 group-hover:h-4 group-hover:w-4 sm:group-hover:h-4.5 sm:group-hover:w-4.5 md:group-hover:h-5 md:group-hover:w-5 transition-all" />
                                </Button>
                            </div>
                        </div>
                    </TooltipTrigger>
                    <TooltipContent side="right" className="max-w-sm p-3">
                        <div className="space-y-1">
                            <p className="font-medium text-sm">Request New Connector</p>
                            <p className="text-xs text-muted-foreground">
                                Opens a form — copy the request or open it in your email client
                            </p>
                        </div>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>

            <Dialog open={open} onOpenChange={handleOpenChange}>
                <DialogContent
                    className={cn(
                        "p-0 overflow-hidden sm:max-w-[520px]",
                        "rounded-xl shadow-2xl border",
                        isDark
                            ? "bg-gray-950/95 backdrop-blur-sm border-gray-800"
                            : "bg-white/95 backdrop-blur-sm border-gray-200",
                    )}
                >
                    {/* Gradient header band */}
                    <div
                        className={cn(
                            "relative px-6 pt-6 pb-5 border-b",
                            isDark
                                ? "border-gray-800 bg-gradient-to-br from-indigo-950/40 via-gray-900 to-gray-950"
                                : "border-gray-200 bg-gradient-to-br from-indigo-50 via-white to-blue-50/60",
                        )}
                    >
                        <DialogHeader className="space-y-0">
                            <div className="flex items-start gap-3">
                                <div
                                    className={cn(
                                        "flex items-center justify-center w-11 h-11 rounded-lg flex-shrink-0 ring-1",
                                        isDark
                                            ? "bg-indigo-500/15 ring-indigo-400/25 text-indigo-300"
                                            : "bg-indigo-500/10 ring-indigo-500/20 text-indigo-600",
                                    )}
                                >
                                    <Sparkles className="w-5 h-5" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <DialogTitle className="text-lg font-semibold leading-tight">
                                        Request a new connector
                                    </DialogTitle>
                                    <DialogDescription className="text-xs mt-1 text-muted-foreground leading-relaxed">
                                        Tell us which app or data source you'd like to see
                                        next. We review every request and ship the most
                                        useful ones first.
                                    </DialogDescription>
                                </div>
                            </div>
                        </DialogHeader>
                    </div>

                    {/* Body */}
                    <div className="px-6 py-5 space-y-5">
                        {/* App name */}
                        <div className="space-y-1.5">
                            <Label
                                htmlFor="connector-name"
                                className="text-xs font-medium text-muted-foreground"
                            >
                                App or data source <span className="text-red-500">*</span>
                            </Label>
                            <Input
                                id="connector-name"
                                placeholder="e.g. Zoho CRM, BambooHR, internal SQL warehouse"
                                value={connectorName}
                                onChange={(e) => setConnectorName(e.target.value)}
                                autoFocus
                                className={cn(
                                    "h-9 text-sm",
                                    isDark
                                        ? "border-gray-700 focus:border-indigo-500 focus-visible:ring-indigo-500"
                                        : "border-gray-300 focus:border-indigo-500 focus-visible:ring-indigo-500",
                                )}
                            />
                            {/* Quick-pick chips */}
                            <div className="flex flex-wrap gap-1.5 pt-1">
                                {POPULAR_REQUESTS.map((name) => (
                                    <button
                                        key={name}
                                        type="button"
                                        onClick={() => setConnectorName(name)}
                                        className={cn(
                                            "px-2 py-0.5 text-[10px] rounded-full border transition-colors",
                                            connectorName === name
                                                ? isDark
                                                    ? "bg-indigo-500/20 border-indigo-400/40 text-indigo-200"
                                                    : "bg-indigo-50 border-indigo-300 text-indigo-700"
                                                : isDark
                                                    ? "bg-gray-900/50 border-gray-700 text-gray-400 hover:border-gray-600 hover:text-gray-300"
                                                    : "bg-gray-50 border-gray-200 text-gray-500 hover:border-gray-300 hover:text-gray-700",
                                        )}
                                    >
                                        {name}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Use case */}
                        <div className="space-y-1.5">
                            <Label
                                htmlFor="use-case"
                                className="text-xs font-medium text-muted-foreground"
                            >
                                Use case <span className="text-red-500">*</span>
                            </Label>
                            <Textarea
                                id="use-case"
                                placeholder="What kind of data lives there? What would you ask once it's searchable?"
                                rows={3}
                                value={useCase}
                                onChange={(e) => setUseCase(e.target.value)}
                                className={cn(
                                    "text-sm resize-none",
                                    isDark
                                        ? "border-gray-700 focus:border-indigo-500 focus-visible:ring-indigo-500"
                                        : "border-gray-300 focus:border-indigo-500 focus-visible:ring-indigo-500",
                                )}
                            />
                        </div>

                        {/* Email */}
                        <div className="space-y-1.5">
                            <Label
                                htmlFor="requester-email"
                                className="text-xs font-medium text-muted-foreground"
                            >
                                Your email{" "}
                                <span className="text-[10px] text-muted-foreground/60 font-normal">
                                    (optional, so we can follow up)
                                </span>
                            </Label>
                            <Input
                                id="requester-email"
                                type="email"
                                placeholder="you@company.com"
                                value={requesterEmail}
                                onChange={(e) => setRequesterEmail(e.target.value)}
                                className={cn(
                                    "h-9 text-sm",
                                    isDark
                                        ? "border-gray-700 focus:border-indigo-500 focus-visible:ring-indigo-500"
                                        : "border-gray-300 focus:border-indigo-500 focus-visible:ring-indigo-500",
                                )}
                            />
                        </div>
                    </div>

                    {/* Footer */}
                    <div
                        className={cn(
                            "px-6 py-4 border-t flex items-center justify-between gap-3",
                            isDark
                                ? "border-gray-800 bg-gray-900/40"
                                : "border-gray-200 bg-gray-50/80",
                        )}
                    >
                        <a
                            href={`mailto:${SUPPORT_EMAIL}`}
                            className="text-[11px] text-muted-foreground hover:text-foreground transition-colors"
                        >
                            or email us directly →{" "}
                            <span className="font-medium">{SUPPORT_EMAIL}</span>
                        </a>
                        <div className="flex items-center gap-2">
                            <Button
                                variant="outline"
                                size="sm"
                                onClick={handleCopy}
                                disabled={formIsEmpty}
                                className={cn(
                                    "gap-1.5 h-8 text-xs",
                                    isDark
                                        ? "border-gray-700 hover:bg-gray-800"
                                        : "border-gray-300 hover:bg-gray-100",
                                )}
                            >
                                {justCopied ? (
                                    <Check className="h-3.5 w-3.5 text-green-500" />
                                ) : (
                                    <Copy className="h-3.5 w-3.5" />
                                )}
                                {justCopied ? "Copied" : "Copy"}
                            </Button>
                            <Button
                                size="sm"
                                onClick={handleSendViaEmail}
                                disabled={formIsEmpty}
                                className={cn(
                                    "gap-1.5 h-8 text-xs",
                                    "bg-indigo-600 hover:bg-indigo-500 text-white",
                                    "disabled:bg-indigo-600/40 disabled:text-white/60",
                                )}
                            >
                                <Mail className="h-3.5 w-3.5" />
                                Send request
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </>
    );
};

export default RequestConnectorButton;
