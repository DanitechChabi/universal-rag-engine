-- Migration 0007 — fournisseurs externes compatibles OpenAI : OpenRouter, Groq, Mistral.
-- Toujours externes. La contrainte compare le texte : une valeur d'énumération ajoutée dans la
-- même transaction ne peut pas encore servir de constante.
ALTER TYPE provider_kind ADD VALUE 'openrouter';
ALTER TYPE provider_kind ADD VALUE 'groq';
ALTER TYPE provider_kind ADD VALUE 'mistral';
ALTER TABLE ai_providers DROP CONSTRAINT ai_providers_check1;
ALTER TABLE ai_providers ADD CONSTRAINT ai_providers_check1
    CHECK (kind::text NOT IN ('anthropic', 'gemini', 'openai', 'openrouter', 'groq', 'mistral') OR locality = 'external');
