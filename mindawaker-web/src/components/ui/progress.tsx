import * as React from 'react';
import * as ProgressPrimitive from '@radix-ui/react-progress';
import { cn } from '@/lib/utils';

const Progress = React.forwardRef<
  React.ElementRef<typeof ProgressPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ProgressPrimitive.Root> & {
    variant?: 'default' | 'gradient' | 'success' | 'warning';
  }
>(({ className, value, variant = 'default', ...props }, ref) => {
  const variantStyles = {
    default: 'bg-primary',
    gradient: 'bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 animate-gradient',
    success: 'bg-green-500',
    warning: 'bg-amber-500',
  };

  return (
    <ProgressPrimitive.Root
      ref={ref}
      className={cn(
        'relative h-4 w-full overflow-hidden rounded-full bg-secondary',
        className
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className={cn('h-full w-full flex-1 transition-all', variantStyles[variant])}
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  );
});
Progress.displayName = ProgressPrimitive.Root.displayName;

export { Progress };
