import * as React from 'react';
import { cn } from '@/lib/utils';

const Textarea = React.forwardRef(({ className, ...props }, ref) => {
  return (
    <textarea
      className={cn(
        'flex min-h-[120px] w-full rounded-xl bg-white/[0.06] px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 shadow-inner backdrop-blur-md transition-all duration-200 focus:border-blue-500/60 focus:bg-[#0f0f14] focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:cursor-not-allowed disabled:opacity-50 resize-y',
        className
      )}
      ref={ref}
      {...props}
    />
  );
});
Textarea.displayName = 'Textarea';

export { Textarea };
