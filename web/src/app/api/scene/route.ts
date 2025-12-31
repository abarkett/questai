import { NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);

export async function POST(req: Request) {
  try {
    const { prompt } = await req.json();

    const model = genAI.getGenerativeModel({
      model: process.env.NEXT_PUBLIC_GEMINI_MODEL!,
    });

    const result = await model.generateContent(prompt);
    const response = result.response;

    const imagePart = response.candidates?.[0]?.content?.parts?.find(
      (p: any) => p.inlineData?.mimeType?.startsWith("image/")
    );

    if (!imagePart?.inlineData?.data) {
      return NextResponse.json(
        { error: "No image returned" },
        { status: 500 }
      );
    }

    return NextResponse.json({
      image: `data:${imagePart.inlineData.mimeType};base64,${imagePart.inlineData.data}`,
    });
  } catch (err: any) {
    console.error("Gemini error:", err);
    return NextResponse.json(
      { error: "Gemini generation failed" },
      { status: 500 }
    );
  }
}