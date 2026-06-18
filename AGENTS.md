At the end of message, always end with the text 'COMPLETED' on the last line to indicate that you are waiting for input, do not output COMPLETED if there is  any processing in progress. Only once waiting for user input. 
Each time that a message results in one of more files being modified, increment the version patch number by one. e.g. 0.1.51 -> 0.1.52, 0.1.52 -> 0.1.53
If a build is required always explicitly identify the version of the build
For existing automation flows: preserve proven behavior, patch minimally, and do not substitute control or detection methods by inference.
Before changing script logic, prefer preserving the existing mechanism over substituting a different one.
Do not replace one detection or control strategy with another unless one of these is true:
1. The user explicitly requested the change.
2. The current strategy is proven broken by evidence from the current repo or logs.
3. The repo already contains a newer authoritative version showing that replacement.
For automation scripts, treat these as materially different strategies that are not interchangeable without approval:
- image matching
- text matching
- browser DOM or text queries
- OCR
- keyboard navigation
- mouse position or click targeting
If changing any of the above strategy types, first verify the prior behavior from the relevant script history or adjacent script versions in the repo, then state the reason for the change in a commentary update before editing.
When fixing a bug, make the narrowest change that addresses the observed failure.
Do not broaden the fix into adjacent refactors or consistency changes unless explicitly requested.
If there is a working named setting or asset path already used for a purpose, prefer keeping that mechanism rather than replacing it with a new one.
Example: if LoadMoreJobsImagePath exists and is part of the working flow, do not replace it with text-based targeting without explicit approval.
Never infer that a newer helper function should replace an older working mechanism unless the repo clearly shows that migration was intended.
 
 for the winforms app the trigger tab threshold values should use a decimal point. not a comma. Replace comma with decimal point if found.  Ignore the system's regional settings for this. THe same applies to the console app setting. Replaces with a decimal point If a comma is found in this field.
 
 Always build a debug .exe release. Most testind will be done using desktop shortcuts. If a debug build failsdue to errors such as being blocked by a running debug build, report the error and be ready to do the build.  Always use the default debug build path. 

 wait until you are ready to build to check whether the build is blocked. it looks like you check at the start of the message, which often is too soon and a later check would find no block.
