# Amazon Bedrock Foundation Models

- AWS profile: `btc-bedrock`
- AWS region: `us-east-1`
- Exported at: `2026-06-02T21:29:22.044096+00:00`
- Total models: `125`

## Models

| # | Model ID | Provider | Model Name | Input | Output | Inference Types | Streaming |
|---:|---|---|---|---|---|---|---|
| 1 | `ai21.jamba-1-5-large-v1:0` | AI21 Labs | Jamba 1.5 Large | TEXT | TEXT | ON_DEMAND | yes |
| 2 | `ai21.jamba-1-5-mini-v1:0` | AI21 Labs | Jamba 1.5 Mini | TEXT | TEXT | ON_DEMAND | yes |
| 3 | `amazon.nova-2-lite-v1:0` | Amazon | Nova 2 Lite | TEXT, IMAGE, VIDEO | TEXT | INFERENCE_PROFILE | yes |
| 4 | `amazon.nova-2-lite-v1:0:256k` | Amazon | Nova 2 Lite | TEXT, IMAGE, VIDEO | TEXT | PROVISIONED | yes |
| 5 | `amazon.nova-2-multimodal-embeddings-v1:0` | Amazon | Amazon Nova Multimodal Embeddings | TEXT, IMAGE, AUDIO, VIDEO | EMBEDDING | ON_DEMAND | no |
| 6 | `amazon.nova-2-sonic-v1:0` | Amazon | Nova 2 Sonic | SPEECH | SPEECH, TEXT | ON_DEMAND | yes |
| 7 | `amazon.nova-canvas-v1:0` | Amazon | Nova Canvas | TEXT, IMAGE | IMAGE | ON_DEMAND, PROVISIONED | no |
| 8 | `amazon.nova-lite-v1:0` | Amazon | Nova Lite | TEXT, IMAGE, VIDEO | TEXT | ON_DEMAND, INFERENCE_PROFILE | yes |
| 9 | `amazon.nova-lite-v1:0:24k` | Amazon | Nova Lite | TEXT, IMAGE, VIDEO | TEXT | PROVISIONED | yes |
| 10 | `amazon.nova-lite-v1:0:300k` | Amazon | Nova Lite | TEXT, IMAGE, VIDEO | TEXT | PROVISIONED | yes |
| 11 | `amazon.nova-micro-v1:0` | Amazon | Nova Micro | TEXT | TEXT | ON_DEMAND, INFERENCE_PROFILE | yes |
| 12 | `amazon.nova-micro-v1:0:128k` | Amazon | Nova Micro | TEXT | TEXT | PROVISIONED | yes |
| 13 | `amazon.nova-micro-v1:0:24k` | Amazon | Nova Micro | TEXT | TEXT | PROVISIONED | yes |
| 14 | `amazon.nova-premier-v1:0` | Amazon | Nova Premier | TEXT, IMAGE, VIDEO | TEXT | INFERENCE_PROFILE | yes |
| 15 | `amazon.nova-premier-v1:0:1000k` | Amazon | Nova Premier | TEXT, IMAGE, VIDEO | TEXT | - | yes |
| 16 | `amazon.nova-premier-v1:0:20k` | Amazon | Nova Premier | TEXT, IMAGE, VIDEO | TEXT | - | yes |
| 17 | `amazon.nova-premier-v1:0:8k` | Amazon | Nova Premier | TEXT, IMAGE, VIDEO | TEXT | - | yes |
| 18 | `amazon.nova-premier-v1:0:mm` | Amazon | Nova Premier | TEXT, IMAGE, VIDEO | TEXT | - | yes |
| 19 | `amazon.nova-pro-v1:0` | Amazon | Nova Pro | TEXT, IMAGE, VIDEO | TEXT | ON_DEMAND, INFERENCE_PROFILE | yes |
| 20 | `amazon.nova-pro-v1:0:24k` | Amazon | Nova Pro | TEXT, IMAGE, VIDEO | TEXT | PROVISIONED | yes |
| 21 | `amazon.nova-pro-v1:0:300k` | Amazon | Nova Pro | TEXT, IMAGE, VIDEO | TEXT | PROVISIONED | yes |
| 22 | `amazon.nova-reel-v1:0` | Amazon | Nova Reel | TEXT, IMAGE | VIDEO | ON_DEMAND | no |
| 23 | `amazon.nova-reel-v1:1` | Amazon | Nova Reel | TEXT, IMAGE | VIDEO | ON_DEMAND | no |
| 24 | `amazon.nova-sonic-v1:0` | Amazon | Nova Sonic | SPEECH | SPEECH, TEXT | ON_DEMAND | yes |
| 25 | `amazon.titan-embed-g1-text-02` | Amazon | Titan Text Embeddings v2 | TEXT | EMBEDDING | ON_DEMAND | no |
| 26 | `amazon.titan-embed-image-v1` | Amazon | Titan Multimodal Embeddings G1 | TEXT, IMAGE | EMBEDDING | ON_DEMAND | no |
| 27 | `amazon.titan-embed-image-v1:0` | Amazon | Titan Multimodal Embeddings G1 | TEXT, IMAGE | EMBEDDING | PROVISIONED | no |
| 28 | `amazon.titan-embed-text-v1` | Amazon | Titan Embeddings G1 - Text | TEXT | EMBEDDING | ON_DEMAND | no |
| 29 | `amazon.titan-embed-text-v1:2:8k` | Amazon | Titan Embeddings G1 - Text | TEXT | EMBEDDING | PROVISIONED | no |
| 30 | `amazon.titan-embed-text-v2:0` | Amazon | Titan Text Embeddings V2 | TEXT | EMBEDDING | ON_DEMAND | no |
| 31 | `amazon.titan-embed-text-v2:0:8k` | Amazon | Titan Text Embeddings V2 | TEXT | EMBEDDING | - | no |
| 32 | `amazon.titan-image-generator-v2:0` | Amazon | Titan Image Generator G1 v2 | TEXT, IMAGE | IMAGE | PROVISIONED, ON_DEMAND | no |
| 33 | `anthropic.claude-3-5-haiku-20241022-v1:0` | Anthropic | Claude 3.5 Haiku | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 34 | `anthropic.claude-3-haiku-20240307-v1:0` | Anthropic | Claude 3 Haiku | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 35 | `anthropic.claude-3-haiku-20240307-v1:0:200k` | Anthropic | Claude 3 Haiku | TEXT, IMAGE | TEXT | PROVISIONED | yes |
| 36 | `anthropic.claude-3-haiku-20240307-v1:0:48k` | Anthropic | Claude 3 Haiku | TEXT, IMAGE | TEXT | PROVISIONED | yes |
| 37 | `anthropic.claude-3-sonnet-20240229-v1:0` | Anthropic | Claude 3 Sonnet | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 38 | `anthropic.claude-3-sonnet-20240229-v1:0:200k` | Anthropic | Claude 3 Sonnet | TEXT, IMAGE | TEXT | PROVISIONED | yes |
| 39 | `anthropic.claude-3-sonnet-20240229-v1:0:28k` | Anthropic | Claude 3 Sonnet | TEXT, IMAGE | TEXT | PROVISIONED | yes |
| 40 | `anthropic.claude-haiku-4-5-20251001-v1:0` | Anthropic | Claude Haiku 4.5 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 41 | `anthropic.claude-opus-4-1-20250805-v1:0` | Anthropic | Claude Opus 4.1 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 42 | `anthropic.claude-opus-4-5-20251101-v1:0` | Anthropic | Claude Opus 4.5 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 43 | `anthropic.claude-opus-4-6-v1` | Anthropic | Claude Opus 4.6 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 44 | `anthropic.claude-opus-4-7` | Anthropic | Claude Opus 4.7 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 45 | `anthropic.claude-opus-4-8` | Anthropic | Claude Opus 4.8 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 46 | `anthropic.claude-sonnet-4-20250514-v1:0` | Anthropic | Claude Sonnet 4 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 47 | `anthropic.claude-sonnet-4-5-20250929-v1:0` | Anthropic | Claude Sonnet 4.5 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 48 | `anthropic.claude-sonnet-4-6` | Anthropic | Claude Sonnet 4.6 | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 49 | `cohere.command-r-plus-v1:0` | Cohere | Command R+ | TEXT | TEXT | ON_DEMAND | yes |
| 50 | `cohere.command-r-v1:0` | Cohere | Command R | TEXT | TEXT | ON_DEMAND | yes |
| 51 | `cohere.embed-english-v3` | Cohere | Embed English | TEXT | EMBEDDING | ON_DEMAND | no |
| 52 | `cohere.embed-english-v3:0:512` | Cohere | Embed English | TEXT | EMBEDDING | PROVISIONED | no |
| 53 | `cohere.embed-multilingual-v3` | Cohere | Embed Multilingual | TEXT | EMBEDDING | ON_DEMAND | no |
| 54 | `cohere.embed-multilingual-v3:0:512` | Cohere | Embed Multilingual | TEXT | EMBEDDING | PROVISIONED | no |
| 55 | `cohere.embed-v4:0` | Cohere | Embed v4 | TEXT, IMAGE | EMBEDDING | ON_DEMAND, INFERENCE_PROFILE | no |
| 56 | `cohere.rerank-v3-5:0` | Cohere | Rerank 3.5 | TEXT | TEXT | ON_DEMAND | no |
| 57 | `deepseek.r1-v1:0` | DeepSeek | DeepSeek-R1 | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 58 | `deepseek.v3.2` | DeepSeek | DeepSeek V3.2 | TEXT | TEXT | ON_DEMAND | yes |
| 59 | `google.gemma-3-12b-it` | Google | Gemma 3 12B IT | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 60 | `google.gemma-3-27b-it` | Google | Gemma 3 27B PT | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 61 | `google.gemma-3-4b-it` | Google | Gemma 3 4B IT | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 62 | `meta.llama3-1-70b-instruct-v1:0` | Meta | Llama 3.1 70B Instruct | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 63 | `meta.llama3-1-8b-instruct-v1:0` | Meta | Llama 3.1 8B Instruct | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 64 | `meta.llama3-2-11b-instruct-v1:0` | Meta | Llama 3.2 11B Instruct | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 65 | `meta.llama3-2-1b-instruct-v1:0` | Meta | Llama 3.2 1B Instruct | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 66 | `meta.llama3-2-3b-instruct-v1:0` | Meta | Llama 3.2 3B Instruct | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 67 | `meta.llama3-2-90b-instruct-v1:0` | Meta | Llama 3.2 90B Instruct | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 68 | `meta.llama3-3-70b-instruct-v1:0` | Meta | Llama 3.3 70B Instruct | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 69 | `meta.llama3-70b-instruct-v1:0` | Meta | Llama 3 70B Instruct | TEXT | TEXT | ON_DEMAND | yes |
| 70 | `meta.llama3-8b-instruct-v1:0` | Meta | Llama 3 8B Instruct | TEXT | TEXT | ON_DEMAND | yes |
| 71 | `meta.llama4-maverick-17b-instruct-v1:0` | Meta | Llama 4 Maverick 17B Instruct | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 72 | `meta.llama4-scout-17b-instruct-v1:0` | Meta | Llama 4 Scout 17B Instruct | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 73 | `minimax.minimax-m2` | MiniMax | MiniMax M2 | TEXT | TEXT | ON_DEMAND | yes |
| 74 | `minimax.minimax-m2.1` | MiniMax | MiniMax M2.1 | TEXT | TEXT | ON_DEMAND | yes |
| 75 | `minimax.minimax-m2.5` | MiniMax | MiniMax M2.5 | TEXT | TEXT | ON_DEMAND | yes |
| 76 | `mistral.devstral-2-123b` | Mistral AI | Devstral 2 123B | TEXT | TEXT | ON_DEMAND | yes |
| 77 | `mistral.magistral-small-2509` | Mistral AI | Magistral Small 2509 | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 78 | `mistral.ministral-3-14b-instruct` | Mistral AI | Ministral 14B 3.0 | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 79 | `mistral.ministral-3-3b-instruct` | Mistral AI | Ministral 3B | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 80 | `mistral.ministral-3-8b-instruct` | Mistral AI | Ministral 3 8B | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 81 | `mistral.mistral-7b-instruct-v0:2` | Mistral AI | Mistral 7B Instruct | TEXT | TEXT | ON_DEMAND | yes |
| 82 | `mistral.mistral-large-2402-v1:0` | Mistral AI | Mistral Large (24.02) | TEXT | TEXT | ON_DEMAND | yes |
| 83 | `mistral.mistral-large-3-675b-instruct` | Mistral AI | Mistral Large 3 | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 84 | `mistral.mistral-small-2402-v1:0` | Mistral AI | Mistral Small (24.02) | TEXT | TEXT | ON_DEMAND | yes |
| 85 | `mistral.mixtral-8x7b-instruct-v0:1` | Mistral AI | Mixtral 8x7B Instruct | TEXT | TEXT | ON_DEMAND | yes |
| 86 | `mistral.pixtral-large-2502-v1:0` | Mistral AI | Pixtral Large (25.02) | TEXT, IMAGE | TEXT | INFERENCE_PROFILE | yes |
| 87 | `mistral.voxtral-mini-3b-2507` | Mistral AI | Voxtral Mini 3B 2507 | SPEECH, TEXT | TEXT | ON_DEMAND | yes |
| 88 | `mistral.voxtral-small-24b-2507` | Mistral AI | Voxtral Small 24B 2507 | SPEECH, TEXT | TEXT | ON_DEMAND | yes |
| 89 | `moonshot.kimi-k2-thinking` | Moonshot AI | Kimi K2 Thinking | TEXT | TEXT | ON_DEMAND | yes |
| 90 | `moonshotai.kimi-k2.5` | Moonshot AI | Kimi K2.5 | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 91 | `nvidia.nemotron-nano-12b-v2` | NVIDIA | NVIDIA Nemotron Nano 12B v2 VL BF16 | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 92 | `nvidia.nemotron-nano-3-30b` | NVIDIA | Nemotron Nano 3 30B | TEXT | TEXT | ON_DEMAND | yes |
| 93 | `nvidia.nemotron-nano-9b-v2` | NVIDIA | NVIDIA Nemotron Nano 9B v2 | TEXT | TEXT | ON_DEMAND | yes |
| 94 | `nvidia.nemotron-super-3-120b` | NVIDIA | NVIDIA Nemotron 3 Super 120B A12B | TEXT | TEXT | ON_DEMAND | yes |
| 95 | `openai.gpt-oss-120b-1:0` | OpenAI | gpt-oss-120b | TEXT | TEXT | ON_DEMAND | yes |
| 96 | `openai.gpt-oss-20b-1:0` | OpenAI | gpt-oss-20b | TEXT | TEXT | ON_DEMAND | yes |
| 97 | `openai.gpt-oss-safeguard-120b` | OpenAI | GPT OSS Safeguard 120B | TEXT | TEXT | ON_DEMAND | yes |
| 98 | `openai.gpt-oss-safeguard-20b` | OpenAI | GPT OSS Safeguard 20B | TEXT | TEXT | ON_DEMAND | yes |
| 99 | `qwen.qwen3-32b-v1:0` | Qwen | Qwen3 32B (dense) | TEXT | TEXT | ON_DEMAND | yes |
| 100 | `qwen.qwen3-coder-30b-a3b-v1:0` | Qwen | Qwen3-Coder-30B-A3B-Instruct | TEXT | TEXT | ON_DEMAND | yes |
| 101 | `qwen.qwen3-coder-next` | Qwen | Qwen3 Coder Next | TEXT | TEXT | ON_DEMAND | yes |
| 102 | `qwen.qwen3-next-80b-a3b` | Qwen | Qwen3 Next 80B A3B | TEXT | TEXT | ON_DEMAND | yes |
| 103 | `qwen.qwen3-vl-235b-a22b` | Qwen | Qwen3 VL 235B A22B | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 104 | `stability.stable-conservative-upscale-v1:0` | Stability AI | Stable Image Conservative Upscale | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 105 | `stability.stable-creative-upscale-v1:0` | Stability AI | Stable Image Creative Upscale | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 106 | `stability.stable-fast-upscale-v1:0` | Stability AI | Stable Image Fast Upscale | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 107 | `stability.stable-image-control-sketch-v1:0` | Stability AI | Stable Image Control Sketch | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 108 | `stability.stable-image-control-structure-v1:0` | Stability AI | Stable Image Control Structure | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 109 | `stability.stable-image-erase-object-v1:0` | Stability AI | Stable Image Erase Object | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 110 | `stability.stable-image-inpaint-v1:0` | Stability AI | Stable Image Inpaint | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 111 | `stability.stable-image-remove-background-v1:0` | Stability AI | Stable Image Remove Background | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 112 | `stability.stable-image-search-recolor-v1:0` | Stability AI | Stable Image Search and Recolor | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 113 | `stability.stable-image-search-replace-v1:0` | Stability AI | Stable Image Search and Replace | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 114 | `stability.stable-image-style-guide-v1:0` | Stability AI | Stable Image Style Guide | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 115 | `stability.stable-outpaint-v1:0` | Stability AI | Stable Image Outpaint | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 116 | `stability.stable-style-transfer-v1:0` | Stability AI | Stable Image Style Transfer | TEXT, IMAGE | IMAGE | INFERENCE_PROFILE | no |
| 117 | `twelvelabs.marengo-embed-2-7-v1:0` | TwelveLabs | Marengo Embed v2.7 | TEXT, IMAGE, SPEECH, VIDEO | EMBEDDING | INFERENCE_PROFILE | no |
| 118 | `twelvelabs.marengo-embed-3-0-v1:0` | TwelveLabs | Marengo Embed 3.0 | TEXT, IMAGE, SPEECH, VIDEO | EMBEDDING | INFERENCE_PROFILE, ON_DEMAND | no |
| 119 | `twelvelabs.pegasus-1-2-v1:0` | TwelveLabs | Pegasus v1.2 | TEXT, VIDEO | TEXT | INFERENCE_PROFILE, ON_DEMAND | yes |
| 120 | `writer.palmyra-vision-7b` | Writer | Writer Palmyra Vision 7B | TEXT, IMAGE | TEXT | ON_DEMAND | yes |
| 121 | `writer.palmyra-x4-v1:0` | Writer | Palmyra X4 | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 122 | `writer.palmyra-x5-v1:0` | Writer | Palmyra X5 | TEXT | TEXT | INFERENCE_PROFILE | yes |
| 123 | `zai.glm-4.7` | Z.AI | GLM 4.7 | TEXT | TEXT | ON_DEMAND | yes |
| 124 | `zai.glm-4.7-flash` | Z.AI | GLM 4.7 Flash | TEXT | TEXT | ON_DEMAND | yes |
| 125 | `zai.glm-5` | Z.AI | GLM 5 | TEXT | TEXT | ON_DEMAND | yes |

## Embedding Models

- `amazon.nova-2-multimodal-embeddings-v1:0` — Amazon / Amazon Nova Multimodal Embeddings
- `amazon.titan-embed-g1-text-02` — Amazon / Titan Text Embeddings v2
- `amazon.titan-embed-image-v1` — Amazon / Titan Multimodal Embeddings G1
- `amazon.titan-embed-image-v1:0` — Amazon / Titan Multimodal Embeddings G1
- `amazon.titan-embed-text-v1` — Amazon / Titan Embeddings G1 - Text
- `amazon.titan-embed-text-v1:2:8k` — Amazon / Titan Embeddings G1 - Text
- `amazon.titan-embed-text-v2:0` — Amazon / Titan Text Embeddings V2
- `amazon.titan-embed-text-v2:0:8k` — Amazon / Titan Text Embeddings V2
- `cohere.embed-english-v3` — Cohere / Embed English
- `cohere.embed-english-v3:0:512` — Cohere / Embed English
- `cohere.embed-multilingual-v3` — Cohere / Embed Multilingual
- `cohere.embed-multilingual-v3:0:512` — Cohere / Embed Multilingual
- `cohere.embed-v4:0` — Cohere / Embed v4
- `twelvelabs.marengo-embed-2-7-v1:0` — TwelveLabs / Marengo Embed v2.7
- `twelvelabs.marengo-embed-3-0-v1:0` — TwelveLabs / Marengo Embed 3.0

## Text / Chat Models

- `ai21.jamba-1-5-large-v1:0` — AI21 Labs / Jamba 1.5 Large
- `ai21.jamba-1-5-mini-v1:0` — AI21 Labs / Jamba 1.5 Mini
- `amazon.nova-2-lite-v1:0` — Amazon / Nova 2 Lite
- `amazon.nova-2-lite-v1:0:256k` — Amazon / Nova 2 Lite
- `amazon.nova-2-sonic-v1:0` — Amazon / Nova 2 Sonic
- `amazon.nova-lite-v1:0` — Amazon / Nova Lite
- `amazon.nova-lite-v1:0:24k` — Amazon / Nova Lite
- `amazon.nova-lite-v1:0:300k` — Amazon / Nova Lite
- `amazon.nova-micro-v1:0` — Amazon / Nova Micro
- `amazon.nova-micro-v1:0:128k` — Amazon / Nova Micro
- `amazon.nova-micro-v1:0:24k` — Amazon / Nova Micro
- `amazon.nova-premier-v1:0` — Amazon / Nova Premier
- `amazon.nova-premier-v1:0:1000k` — Amazon / Nova Premier
- `amazon.nova-premier-v1:0:20k` — Amazon / Nova Premier
- `amazon.nova-premier-v1:0:8k` — Amazon / Nova Premier
- `amazon.nova-premier-v1:0:mm` — Amazon / Nova Premier
- `amazon.nova-pro-v1:0` — Amazon / Nova Pro
- `amazon.nova-pro-v1:0:24k` — Amazon / Nova Pro
- `amazon.nova-pro-v1:0:300k` — Amazon / Nova Pro
- `amazon.nova-sonic-v1:0` — Amazon / Nova Sonic
- `anthropic.claude-3-5-haiku-20241022-v1:0` — Anthropic / Claude 3.5 Haiku
- `anthropic.claude-3-haiku-20240307-v1:0` — Anthropic / Claude 3 Haiku
- `anthropic.claude-3-haiku-20240307-v1:0:200k` — Anthropic / Claude 3 Haiku
- `anthropic.claude-3-haiku-20240307-v1:0:48k` — Anthropic / Claude 3 Haiku
- `anthropic.claude-3-sonnet-20240229-v1:0` — Anthropic / Claude 3 Sonnet
- `anthropic.claude-3-sonnet-20240229-v1:0:200k` — Anthropic / Claude 3 Sonnet
- `anthropic.claude-3-sonnet-20240229-v1:0:28k` — Anthropic / Claude 3 Sonnet
- `anthropic.claude-haiku-4-5-20251001-v1:0` — Anthropic / Claude Haiku 4.5
- `anthropic.claude-opus-4-1-20250805-v1:0` — Anthropic / Claude Opus 4.1
- `anthropic.claude-opus-4-5-20251101-v1:0` — Anthropic / Claude Opus 4.5
- `anthropic.claude-opus-4-6-v1` — Anthropic / Claude Opus 4.6
- `anthropic.claude-opus-4-7` — Anthropic / Claude Opus 4.7
- `anthropic.claude-opus-4-8` — Anthropic / Claude Opus 4.8
- `anthropic.claude-sonnet-4-20250514-v1:0` — Anthropic / Claude Sonnet 4
- `anthropic.claude-sonnet-4-5-20250929-v1:0` — Anthropic / Claude Sonnet 4.5
- `anthropic.claude-sonnet-4-6` — Anthropic / Claude Sonnet 4.6
- `cohere.command-r-plus-v1:0` — Cohere / Command R+
- `cohere.command-r-v1:0` — Cohere / Command R
- `cohere.rerank-v3-5:0` — Cohere / Rerank 3.5
- `deepseek.r1-v1:0` — DeepSeek / DeepSeek-R1
- `deepseek.v3.2` — DeepSeek / DeepSeek V3.2
- `google.gemma-3-12b-it` — Google / Gemma 3 12B IT
- `google.gemma-3-27b-it` — Google / Gemma 3 27B PT
- `google.gemma-3-4b-it` — Google / Gemma 3 4B IT
- `meta.llama3-1-70b-instruct-v1:0` — Meta / Llama 3.1 70B Instruct
- `meta.llama3-1-8b-instruct-v1:0` — Meta / Llama 3.1 8B Instruct
- `meta.llama3-2-11b-instruct-v1:0` — Meta / Llama 3.2 11B Instruct
- `meta.llama3-2-1b-instruct-v1:0` — Meta / Llama 3.2 1B Instruct
- `meta.llama3-2-3b-instruct-v1:0` — Meta / Llama 3.2 3B Instruct
- `meta.llama3-2-90b-instruct-v1:0` — Meta / Llama 3.2 90B Instruct
- `meta.llama3-3-70b-instruct-v1:0` — Meta / Llama 3.3 70B Instruct
- `meta.llama3-70b-instruct-v1:0` — Meta / Llama 3 70B Instruct
- `meta.llama3-8b-instruct-v1:0` — Meta / Llama 3 8B Instruct
- `meta.llama4-maverick-17b-instruct-v1:0` — Meta / Llama 4 Maverick 17B Instruct
- `meta.llama4-scout-17b-instruct-v1:0` — Meta / Llama 4 Scout 17B Instruct
- `minimax.minimax-m2` — MiniMax / MiniMax M2
- `minimax.minimax-m2.1` — MiniMax / MiniMax M2.1
- `minimax.minimax-m2.5` — MiniMax / MiniMax M2.5
- `mistral.devstral-2-123b` — Mistral AI / Devstral 2 123B
- `mistral.magistral-small-2509` — Mistral AI / Magistral Small 2509
- `mistral.ministral-3-14b-instruct` — Mistral AI / Ministral 14B 3.0
- `mistral.ministral-3-3b-instruct` — Mistral AI / Ministral 3B
- `mistral.ministral-3-8b-instruct` — Mistral AI / Ministral 3 8B
- `mistral.mistral-7b-instruct-v0:2` — Mistral AI / Mistral 7B Instruct
- `mistral.mistral-large-2402-v1:0` — Mistral AI / Mistral Large (24.02)
- `mistral.mistral-large-3-675b-instruct` — Mistral AI / Mistral Large 3
- `mistral.mistral-small-2402-v1:0` — Mistral AI / Mistral Small (24.02)
- `mistral.mixtral-8x7b-instruct-v0:1` — Mistral AI / Mixtral 8x7B Instruct
- `mistral.pixtral-large-2502-v1:0` — Mistral AI / Pixtral Large (25.02)
- `mistral.voxtral-mini-3b-2507` — Mistral AI / Voxtral Mini 3B 2507
- `mistral.voxtral-small-24b-2507` — Mistral AI / Voxtral Small 24B 2507
- `moonshot.kimi-k2-thinking` — Moonshot AI / Kimi K2 Thinking
- `moonshotai.kimi-k2.5` — Moonshot AI / Kimi K2.5
- `nvidia.nemotron-nano-12b-v2` — NVIDIA / NVIDIA Nemotron Nano 12B v2 VL BF16
- `nvidia.nemotron-nano-3-30b` — NVIDIA / Nemotron Nano 3 30B
- `nvidia.nemotron-nano-9b-v2` — NVIDIA / NVIDIA Nemotron Nano 9B v2
- `nvidia.nemotron-super-3-120b` — NVIDIA / NVIDIA Nemotron 3 Super 120B A12B
- `openai.gpt-oss-120b-1:0` — OpenAI / gpt-oss-120b
- `openai.gpt-oss-20b-1:0` — OpenAI / gpt-oss-20b
- `openai.gpt-oss-safeguard-120b` — OpenAI / GPT OSS Safeguard 120B
- `openai.gpt-oss-safeguard-20b` — OpenAI / GPT OSS Safeguard 20B
- `qwen.qwen3-32b-v1:0` — Qwen / Qwen3 32B (dense)
- `qwen.qwen3-coder-30b-a3b-v1:0` — Qwen / Qwen3-Coder-30B-A3B-Instruct
- `qwen.qwen3-coder-next` — Qwen / Qwen3 Coder Next
- `qwen.qwen3-next-80b-a3b` — Qwen / Qwen3 Next 80B A3B
- `qwen.qwen3-vl-235b-a22b` — Qwen / Qwen3 VL 235B A22B
- `twelvelabs.pegasus-1-2-v1:0` — TwelveLabs / Pegasus v1.2
- `writer.palmyra-vision-7b` — Writer / Writer Palmyra Vision 7B
- `writer.palmyra-x4-v1:0` — Writer / Palmyra X4
- `writer.palmyra-x5-v1:0` — Writer / Palmyra X5
- `zai.glm-4.7` — Z.AI / GLM 4.7
- `zai.glm-4.7-flash` — Z.AI / GLM 4.7 Flash
- `zai.glm-5` — Z.AI / GLM 5