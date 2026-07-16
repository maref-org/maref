import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // Fix 15: ignore build artifacts that produce false ESLint errors.
  // src-tauri/target/ contains compiled .js files (tauri-codegen-assets)
  // that can't be parsed as UTF-8, causing "Parsing error: Unexpected
  // character" and wasting LLM calls trying to fix binary files.
  globalIgnores(['dist', 'src-tauri/target', 'node_modules', 'build']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
  },
])
