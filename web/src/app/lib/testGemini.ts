import { GoogleGenerativeAI } from "@google/generative-ai";

const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY!);

async function test() {
  const model = genAI.getGenerativeModel({
    model: "gemini-2.0-flash-image-preview",
  });

  const result = await model.generateContent(
    "Fantasy RPG illustration of a dark forest with giant rats, painted style"
  );

  console.log(result.response);
}

test();