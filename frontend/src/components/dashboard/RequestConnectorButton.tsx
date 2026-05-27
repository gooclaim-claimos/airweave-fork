import { Button } from "@/components/ui/button";
import { Plug, Plus } from "lucide-react";
import { useTheme } from "@/lib/theme-provider";
import { cn } from "@/lib/utils";
import { IS_GOOCLAIM_TENANT } from "@/config/env";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";

interface RequestConnectorButtonProps {
    onClick?: () => void;
}

export const RequestConnectorButton = ({ onClick }: RequestConnectorButtonProps) => {
    const { resolvedTheme } = useTheme();
    const isDark = resolvedTheme === 'dark';

    const handleClick = () => {
        if (onClick) {
            onClick();
        } else if (IS_GOOCLAIM_TENANT) {
            window.open('mailto:support@gooclaim.com?subject=Connector%20Request', '_blank');
        } else {
            window.open('https://github.com/gooclaim.com/airweave/issues/new?labels=connector-request&template=connector_request.md&title=[Connector%20Request]%20', '_blank');
        }
    };

    return (
        <TooltipProvider delayDuration={100}>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div
                        className={cn(
                            "border rounded-lg overflow-hidden group transition-all min-w-[150px] cursor-pointer opacity-60 hover:opacity-80",
                            isDark
                                ? "border-gray-800 hover:border-gray-700 bg-gray-900/30 hover:bg-gray-900/50"
                                : "border-gray-300 hover:border-gray-300 bg-gray-50 hover:bg-gray-100"
                        )}
                        onClick={handleClick}
                    >
                        <div className="p-2 sm:p-3 md:p-4 flex items-center justify-between">
                            <div className="flex items-center gap-2 sm:gap-3">
                                <div className={cn(
                                    "flex items-center justify-center w-8 h-8 sm:w-9 sm:h-9 md:w-10 md:h-10 rounded-md flex-shrink-0",
                                    isDark ? "bg-gray-600" : "bg-gray-300"
                                )}>
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
                                        : "bg-gray-100/80 text-gray-600 hover:bg-gray-200/80 hover:text-gray-700 group-hover:bg-gray-200/80"
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
                            {IS_GOOCLAIM_TENANT ? 'Opens email to submit your request' : 'Opens GitHub to submit your request'}
                        </p>
                    </div>
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
};

export default RequestConnectorButton;
