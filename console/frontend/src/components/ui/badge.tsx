import { type VariantProps, cva } from "class-variance-authority"
import type * as React from "react"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border border-border/50 px-2.5 py-0.5 text-xs font-semibold transition-colors shadow-sm backdrop-blur-sm",
  {
    variants: {
      variant: {
        default: "border-primary/20 bg-primary/15 text-primary",
        secondary: "border-secondary-foreground/10 bg-secondary/30 text-secondary-foreground",
        caution: "border-caution-foreground/20 bg-caution/40 text-caution-foreground",
        destructive: "border-destructive/20 bg-destructive/15 text-destructive-foreground",
        outline: "text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
