Regression fixtures: every hard case the packer, checks or step planner got wrong.

- `*.py`: hand-written designs (DSL). Optional `EXPECT = {...}` pins stats values.
- `*.npz`: voxel grids captured from property-test failures (`V`, `palette`, `note`, optional
  `expect` as a JSON string).

`tests/test_fixtures.py` builds each one and runs the independent invariant oracles in
`tests/oracles.py`. Fixtures are expected to PASS unless their EXPECT says otherwise.
