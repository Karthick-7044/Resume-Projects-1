import * as React from 'react';
import { cn } from '@/lib/utils';

const Input = React.forwardRef(({ className, type, ...props }, ref) => {
  return (
    <input
      type={type}
      className={cn(
        'flex h-11 w-full rounded-xl bg-white/[0.06] px-4 py-2 text-sm text-slate-100 placeholder:text-slate-500 shadow-inner backdrop-blur-md transition-all duration-200 focus:border-blue-500/60 focus:bg-[#0f0f14] focus:outline-none focus:ring-2 focus:ring-blue-500/20 disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      ref={ref}
      {...props}
    />
  );
});
Input.displayName = 'Input';

export { Input };
