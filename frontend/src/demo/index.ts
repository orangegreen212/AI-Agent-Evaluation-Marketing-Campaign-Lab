/**
 * Public re-exports for the demo fixture layer.
 *
 * Importing from '@/demo' keeps a single, clearly-labelled entry point to all
 * fabricated data so it cannot be confused with live API responses.
 */

export {
  DEMO_LABEL,
  demoModels,
  demoTestSuites,
  demoAnalyze,
  demoEvaluate,
  demoCompare,
} from './fixtures';
