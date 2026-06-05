import { Slider as SliderPrimitive } from "radix-ui";
import * as React from "react";

import { cn } from "@/lib/utils";

function Slider({
	className,
	defaultValue,
	value,
	min = 0,
	max = 100,
	...props
}: React.ComponentProps<typeof SliderPrimitive.Root>) {
	const _values = React.useMemo(
		() =>
			Array.isArray(value)
				? value
				: Array.isArray(defaultValue)
					? defaultValue
					: [min, max],
		[value, defaultValue, min, max]
	);

	return (
		<SliderPrimitive.Root
			className={cn(
				"data-vertical:min-h-40 relative flex w-full touch-none items-center select-none data-disabled:opacity-50 data-vertical:h-full data-vertical:w-auto data-vertical:flex-col",
				className
			)}
			data-slot="slider"
			defaultValue={defaultValue}
			max={max}
			min={min}
			value={value}
			{...props}
		>
			<SliderPrimitive.Track
				className="bg-muted rounded-full data-horizontal:h-1.5 data-horizontal:w-full data-vertical:h-full data-vertical:w-1.5 bg-muted relative grow overflow-hidden data-horizontal:w-full data-vertical:h-full"
				data-slot="slider-track"
			>
				<SliderPrimitive.Range
					className="bg-primary absolute select-none data-horizontal:h-full data-vertical:w-full"
					data-slot="slider-range"
				/>
			</SliderPrimitive.Track>
			{Array.from({ length: _values.length }, (_, index) => (
				<SliderPrimitive.Thumb
					className="border-primary ring-ring/50 size-4 rounded-full border bg-white shadow-sm transition-[color,box-shadow] hover:ring-4 focus-visible:ring-4 focus-visible:outline-hidden block shrink-0 select-none disabled:pointer-events-none disabled:opacity-50"
					data-slot="slider-thumb"
					key={index}
				/>
			))}
		</SliderPrimitive.Root>
	);
}

export { Slider };
