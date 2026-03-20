"use client";

import * as React from "react";
import { GripVerticalIcon } from "lucide-react";
import { Group, Panel, Separator } from "react-resizable-panels";

import { cn } from "@/lib/utils";

function ResizablePanelGroup({
  className,
  ...props
}: React.ComponentProps<typeof Group>) {
  return (
    <Group
      className={cn("h-full w-full", className)}
      {...props}
    />
  );
}

function ResizablePanel({
  ...props
}: React.ComponentProps<typeof Panel>) {
  return <Panel {...props} />;
}

function ResizableHandle({
  withHandle,
  invisible,
  className,
  orientation = "horizontal",
  ...props
}: React.ComponentProps<typeof Separator> & {
  withHandle?: boolean;
  invisible?: boolean;
  orientation?: "horizontal" | "vertical";
}) {
  const isVertical = orientation === "vertical";

  if (invisible) {
    return (
      <Separator
        className={cn(
          "relative flex items-center justify-center bg-transparent",
          isVertical
            ? "h-0 w-full cursor-row-resize after:absolute after:left-0 after:h-3 after:w-full after:-translate-y-1/2"
            : "w-0 h-full cursor-col-resize after:absolute after:inset-y-0 after:left-1/2 after:w-3 after:-translate-x-1/2",
          className,
        )}
        {...props}
      />
    );
  }

  return (
    <Separator
      className={cn(
        "relative flex items-center justify-center bg-border transition-colors hover:bg-primary/30",
        isVertical ? "h-px w-full" : "w-px h-full",
        "after:absolute",
        isVertical
          ? "after:left-0 after:h-1 after:w-full after:-translate-y-1/2"
          : "after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2",
        className,
      )}
      {...props}
    >
      {withHandle && (
        <div className={cn(
          "z-10 flex items-center justify-center rounded-sm border bg-border",
          isVertical ? "h-3 w-4 rotate-90" : "h-4 w-3",
        )}>
          <GripVerticalIcon className="size-2.5" />
        </div>
      )}
    </Separator>
  );
}

export { ResizablePanelGroup, ResizablePanel, ResizableHandle };
