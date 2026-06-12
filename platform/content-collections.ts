import { defineCollection, defineConfig } from "@content-collections/core";
import { compileMDX } from "@content-collections/mdx";
import remarkGfm from "remark-gfm";
import { z } from "zod";

const blogs = defineCollection({
	name: "blogs",
	directory: "content/blogs",
	include: "**/*.{md,mdx}",
	schema: z.object({
		title: z.string(),
		description: z.string().optional(),
		date: z.string(),
		author: z.string().optional(),
		published: z.boolean().default(true),
		content: z.string(),
	}),
	transform: async (document, context) => {
		const mdx = await compileMDX(context, document, {
			remarkPlugins: [remarkGfm],
		});
		return {
			...document,
			mdx,
		};
	},
});

const terms = defineCollection({
	name: "terms",
	directory: "content/terms",
	include: "**/*.{md,mdx}",
	schema: z.object({
		title: z.string(),
		description: z.string().optional(),
		date: z.string(),
		published: z.boolean().default(true),
		content: z.string(),
	}),
	transform: async (document, context) => {
		const mdx = await compileMDX(context, document, {
			remarkPlugins: [remarkGfm],
		});
		return {
			...document,
			mdx,
		};
	},
});

const privacy = defineCollection({
	name: "privacy",
	directory: "content/privacy",
	include: "**/*.{md,mdx}",
	schema: z.object({
		title: z.string(),
		description: z.string().optional(),
		date: z.string(),
		published: z.boolean().default(true),
		content: z.string(),
	}),
	transform: async (document, context) => {
		const mdx = await compileMDX(context, document, {
			remarkPlugins: [remarkGfm],
		});
		return {
			...document,
			mdx,
		};
	},
});

const changelog = defineCollection({
	name: "changelog",
	directory: "content/changelog",
	include: "**/*.{md,mdx}",
	schema: z.object({
		title: z.string(),
		description: z.string().optional(),
		date: z.string(),
		version: z.string().optional(),
		published: z.boolean().default(true),
		content: z.string(),
	}),
	transform: async (document, context) => {
		const mdx = await compileMDX(context, document, {
			remarkPlugins: [remarkGfm],
		});
		return {
			...document,
			mdx,
		};
	},
});

export default defineConfig({
	content: [blogs, terms, privacy, changelog],
});
