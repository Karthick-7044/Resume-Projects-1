import * as React from 'react';
import { cva } from 'class-variance-authority';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  'inline-flex items-center justify-center whitespace-nowrap rounded-full text-sm font-medium transition-all duration-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/50 disabled:pointer-events-none disabled:opacity-50 active:scale-[0.98]',
  {
    variants: {
      variant: {
        default:
          'bg-white text-black font-medium hover:bg-indigo-100 shadow-[0_10px_40px_-12px_rgba(165,180,252,0.7)] hover:-translate-y-0.5',
        secondary:
          'bg-white/[0.06] text-slate-100 hover:bg-white/[0.11] backdrop-blur-md',
        outline:
          'bg-transparent text-slate-100 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.18)] hover:shadow-[inset_0_0_0_1px_rgba(255,255,255,0.4)] hover:bg-white/[0.04]',
        ghost:
          'text-slate-300 hover:text-white hover:bg-white/5',
        glass:
          'bg-white/[0.06] backdrop-blur-md text-white hover:bg-white/[0.12]',
        cyan:
          'bg-gradient-to-r from-cyan-300 to-indigo-300 text-slate-950 font-semibold hover:brightness-110 hover:-translate-y-0.5',
      },
      size: {
        default: 'h-11 px-6 py-2',
        sm: 'h-9 px-4 py-1.5 text-xs',
        lg: 'h-13 px-8 py-3 text-base',
        icon: 'h-10 w-10 p-0',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  }
);

const Button = React.forwardRef(({ className, variant, size, children, ...props }, ref) => {
  return (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}
    >
      {children}
    </button>
  );
});

Button.displayName = 'Button';

export { Button, buttonVariants };
