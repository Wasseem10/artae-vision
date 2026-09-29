process.env.ARTAE_BENCHMARK_DETECTOR = 'multi';
process.env.ARTAE_BENCHMARK_DATASET ||= 'caucafall';
require('./run-urfall-benchmark.cjs');
