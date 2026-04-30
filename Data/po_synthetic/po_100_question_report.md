# PO CSV QA Consolidated Report

Generated: 2026-04-30T18:36:51.595Z

## Scope

Only these two CSV data sources were active and used:
- po_with_cost_center
- po_with_wbs_element

Queryable tables verified:
- po_with_cost_center_4abd3763__po_with_cost_center
- po_with_wbs_element_1dc2a327__po_with_wbs_element

Synthetic files:
- /Users/tomman/TIDY/SABIC/GenericChatWithSQLData/Data/po_synthetic/po_with_cost_center.csv (52,015 data rows, 9 columns)
- /Users/tomman/TIDY/SABIC/GenericChatWithSQLData/Data/po_synthetic/po_with_wbs_element.csv (18,015 data rows, 8 columns)

## Verification Summary

- Full live 113-question run: 104 passed, 9 failed while backend fixes/reloads were happening.
- Clean rerun of the 9 failed questions on the final loaded backend: all passed (8/9 together, then the final data-quality case passed 1/1 after the last prompt hardening).
- Backend tests: 16 passed.
- Frontend production build: passed.
- Open failures: 0 in the final targeted verification set.

## Questions Asked

1. What data is available in these two PO tables?
2. Show row counts for both tables.
3. List the columns and what each table appears to represent.
4. What are the earliest and latest creation dates in each table?
5. How many distinct purchase orders are in each table?
6. How many distinct PO number and item combinations are in each table?
7. Show the distinct company codes in both tables.
8. Show distinct plants across both tables in a table.
9. Which plants have missing values in either table?
10. How many rows have missing plant values by table?
11. Which function areas appear in the WBS table?
12. Which function areas appear in the cost center table?
13. Compare row counts by function area text across the two tables.
14. Top 10 function areas by row count in the cost center table.
15. Top 10 function areas by row count in the WBS table.
16. Which function area has the most purchase order items overall?
17. Show counts by company code and table.
18. Show counts by plant and table, sorted highest first.
19. Which plant has the most cost center rows?
20. Which plant has the most WBS rows?
21. Show yearly PO creation trend for both tables.
22. Show monthly trend for 2026 in both tables.
23. Which year has the highest number of PO items in the cost center table?
24. Which year has the highest number of PO items in the WBS table?
25. Show the latest 20 PO items from the cost center table.
26. Show the latest 20 PO items from the WBS table.
27. Show the oldest 20 PO items from both tables combined.
28. Find duplicate PO number and item rows in the cost center table.
29. Find duplicate PO number and item rows in the WBS table.
30. Which PO numbers have the most line items in the cost center table?
31. Which PO numbers have the most line items in the WBS table?
32. How many PO item combinations exist in both tables?
33. How many PO item combinations are only in the WBS table?
34. How many PO item combinations are only in the cost center table?
35. Show sample PO items that exist in both tables.
36. Show sample PO items that exist only in the WBS table.
37. Show sample PO items that exist only in the cost center table.
38. Join the two tables on PO number and item and compare plant values.
39. Find PO items where plant differs between the two tables.
40. Find PO items where company code differs between the two tables.
41. Find PO items where function area differs between the two tables.
42. Find PO items where function area text differs between the two tables.
43. Compare cost_center_wbs to cost_center for matching PO items.
44. How many matching PO items have the same cost center and WBS cost center?
45. How many matching PO items have different cost center and WBS cost center?
46. Show the top cost centers by number of PO items.
47. Show the top WBS cost centers by number of PO items.
48. Which cost centers appear in both cost_center and cost_center_wbs?
49. Which cost centers appear only as WBS cost centers?
50. Which cost centers appear only as normal cost centers?
51. Show function area distribution for cost centers that appear in both tables.
52. Show plant distribution for PO items that appear in both tables.
53. Which company code has the highest overlap between the two tables?
54. Which plant has the highest overlap between the two tables?
55. Show percentage overlap by company code between the two tables.
56. Show percentage overlap by plant between the two tables.
57. For company code 1000, show PO item counts by function area across both tables.
58. For plant 1033, compare cost center and WBS rows by function area.
59. For plant 1000, what are the top 10 cost centers?
60. For plant 10M1, what function areas are represented?
61. Show rows where func_area is missing in the cost center table.
62. Show rows where func_area_txt is missing in the cost center table.
63. Are there any missing func_area values in the WBS table?
64. Find cost center rows where ekkn_kostl and cost_center are different.
65. How many rows have ekkn_kostl different from cost_center by function area?
66. Show the top plants where ekkn_kostl differs from cost_center.
67. Show company code and plant combinations with the most rows.
68. Which function area text maps to more than one function area code?
69. Which function area code maps to more than one function area text?
70. List all function area codes with their text labels.
71. Show count of PO items by company code, plant, and year.
72. Rank plants by number of distinct PO numbers.
73. Rank function areas by number of distinct PO numbers.
74. Show PO numbers that appear with more than five items.
75. Show PO numbers that appear in both tables with more than three items.
76. Find matching PO items created on different dates across the two tables.
77. Find matching PO items where creation dates are the same.
78. Show the date range by company code for each table.
79. Show the date range by plant for each table.
80. What are the most common PO item numbers in each table?
81. Show cost center table counts by PO item number.
82. Show WBS table counts by PO item number.
83. Which PO item number has the highest overlap between tables?
84. For Information Technology, compare rows by plant across both tables.
85. For Manufacturing Support, compare rows by plant across both tables.
86. For Corporate Affairs, show yearly trend in both tables.
87. For Digitization, list the top cost centers and WBS cost centers.
88. Which functional areas exist in WBS but not in cost center?
89. Which functional areas exist in cost center but not in WBS?
90. Show a data quality summary for both tables.
91. Show a join quality summary between the two PO tables.
92. What questions can I ask about these PO tables?
93. Give me three executive insights from these two tables.
94. Show the top 5 plants by cost center row count. [followup-1, turn 1]
95. Now show the same plants from the WBS table. [followup-1, turn 2]
96. Compare those side by side and sort by the largest difference. [followup-1, turn 3]
97. Only show differences greater than 500 rows. [followup-1, turn 4]
98. Which function areas have the most matching PO items across both tables? [followup-2, turn 1]
99. Now break the top function area down by plant. [followup-2, turn 2]
100. Show that as a chart-ready table sorted highest first. [followup-2, turn 3]
101. Now include company code in that breakdown. [followup-2, turn 4]
102. Find PO item combinations where cost_center_wbs is different from cost_center. [followup-3, turn 1]
103. Show the top 10 mismatches by function area. [followup-3, turn 2]
104. Now only show company code 1000. [followup-3, turn 3]
105. For those results, summarize the data quality issue in plain language. [followup-3, turn 4]
106. Show yearly counts for both tables. [followup-4, turn 1]
107. Now focus on the latest year only. [followup-4, turn 2]
108. Break that latest year down by month and table. [followup-4, turn 3]
109. Which month had the highest combined PO item count? [followup-4, turn 4]
110. List PO numbers that appear in both tables with multiple items. [followup-5, turn 1]
111. Pick the PO with the most items and show its line details. [followup-5, turn 2]
112. Now compare its function areas across the two tables. [followup-5, turn 3]
113. Are there any inconsistencies for that PO? [followup-5, turn 4]
