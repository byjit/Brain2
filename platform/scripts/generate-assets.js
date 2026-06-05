import fs from "fs";
import { Anchor } from "lucide-react";
import path from "path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import sharp from "sharp";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const SIZE = 512;
const COLOR = "#000000"; // Matching manifest theme_color

// Create the element
// increasing stroke width slightly for better visibility at small sizes if needed, but 2 is standard.
const element = React.createElement(Anchor, {
	size: SIZE,
	color: COLOR,
	strokeWidth: 2,
});

const svgString = renderToStaticMarkup(element);
const svgBuffer = Buffer.from(svgString);

async function generate() {
	const publicDir = path.resolve(__dirname, "../public");

	if (!fs.existsSync(publicDir)) {
		fs.mkdirSync(publicDir, { recursive: true });
	}

	console.log("Generating assets from LogoIcon (Anchor)...");

	// logo512.png
	await sharp(svgBuffer)
		.resize(512, 512)
		.png()
		.toFile(path.join(publicDir, "logo512.png"));
	console.log("Generated logo512.png");

	// logo192.png
	await sharp(svgBuffer)
		.resize(192, 192)
		.png()
		.toFile(path.join(publicDir, "logo192.png"));
	console.log("Generated logo192.png");

	// favicon.ico (32x32 PNG)
	await sharp(svgBuffer)
		.resize(32, 32)
		.png()
		.toFile(path.join(publicDir, "favicon.ico"));
	console.log("Generated favicon.ico");
}

generate().catch((err) => {
	console.error("Error generating assets:", err);
	process.exit(1);
});
