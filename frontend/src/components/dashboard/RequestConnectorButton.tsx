import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Plug, Plus, Copy, Mail } from "lucide-react";
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

const buildEmailBody = (
    connectorName: string,
    useCase: string,
    requesterEmail: string,
) => {
    const lines = [
        `Connector / App: ${connectorName || "(not specified)"}`,
        "",
        "Use case:",
        useCase || "(not specified)",
        "",
        `Requested by: ${requesterEmail || "(not specified)"}`,
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
        const payload = `To: ${SUPPORT_EMAIL}\nSubject: Connector Request — ${connectorName.trim() || "untitled"}\n\n${body}`;
        try {
            await navigator.clipboard.writeText(payload);
            toast.success("Request copied — paste it into your email client");
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
        // Use location.href, NOT window.open(url, '_blank'). The latter
        // opens a brand-new blank tab that stays blank if the user has no
        // system mailto handler configured — the original bug this modal
        // replaces. location.href just hands the URL to the OS handler.
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
                                Opens a form — submit via email or copy the request
                            </p>
                        </div>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>Request a New Connector</DialogTitle>
                        <DialogDescription>
                            Tell us which app or data source you'd like to see, and we'll
                            evaluate adding it. You can submit via email or copy the
                            request to send manually.
                        </DialogDescription>
                    </DialogHeader>

                    <div className="space-y-4 py-2">
                        <div className="space-y-2">
                            <Label htmlFor="connector-name">App or data source name</Label>
                            <Input
                                id="connector-name"
                                placeholder="e.g. Zoho CRM, BambooHR, internal SQL warehouse"
                                value={connectorName}
                                onChange={(e) => setConnectorName(e.target.value)}
                                autoFocus
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="use-case">Use case</Label>
                            <Textarea
                                id="use-case"
                                placeholder="What kind of data lives there? How would you search it?"
                                rows={3}
                                value={useCase}
                                onChange={(e) => setUseCase(e.target.value)}
                            />
                        </div>

                        <div className="space-y-2">
                            <Label htmlFor="requester-email">Your email (optional)</Label>
                            <Input
                                id="requester-email"
                                type="email"
                                placeholder="So we can follow up"
                                value={requesterEmail}
                                onChange={(e) => setRequesterEmail(e.target.value)}
                            />
                        </div>
                    </div>

                    <DialogFooter className="gap-2 sm:gap-0">
                        <Button
                            variant="outline"
                            onClick={handleCopy}
                            disabled={formIsEmpty}
                            className="gap-2"
                        >
                            <Copy className="h-4 w-4" />
                            Copy Request
                        </Button>
                        <Button
                            onClick={handleSendViaEmail}
                            disabled={formIsEmpty}
                            className="gap-2"
                        >
                            <Mail className="h-4 w-4" />
                            Open in Email
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
};

export default RequestConnectorButton;
