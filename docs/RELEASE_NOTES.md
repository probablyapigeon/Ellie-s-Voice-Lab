Ellie's Voice Lab 0.2.0 adds deterministic controls and learners.

Download **BirdVoiceLab-0.2.0-Windows.zip**, extract the entire ZIP, then open **BirdVoiceLab.exe** inside the folder. No Python installation is needed. Use **Explore a synthetic example** to try the notebook first, and **Quit application** to stop it.

New observation studies include ten precommitted controls: the original six probabilistic comparisons plus deterministic first-position, brightest-symbol, most-frequent-choice and context-learning rules. The learner updates only from earlier assessed selections in a matching context. Decision traces show its values and updates. Existing 0.1 studies keep their original six controls and data folder.

The sandbox now compares five policies: stochastic learner, its learning-disabled control, random choice, deterministic learner, and its learning-disabled control. Deterministic policies use no random draws and fixed tie rules; changing the seed leaves their full traces unchanged.

Reports show exact matches and zero-probability responses alongside Brier score and log loss. Displayed log loss uses a declared probability floor of 10^-15 rather than concealing its treatment of impossible predictions.

Validation: 16 automated tests and the complete browser workflow passed. The rebuilt Windows executable was tested with bundled assets, demo, exports, simulation, quit, and evidence verification. The Windows build is unsigned; macOS/Linux source use is untested.

These controls test specified alternative explanations. They do not establish that a bird is deterministic or independently prove intention. Observations and corroboration are manually entered; later adjudication still requires external annotations. No automatic vocalization recognition is included.

Source ZIP and SHA256 checksums are included below. See the repository README and guide for Jen for details.
