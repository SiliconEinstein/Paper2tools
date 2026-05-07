example1 = {
    "step_id": 1,
    "logic_description": "自然语言描述解题逻辑",
    "tool_intent": "工具功能意图描述",
    "suggested_tools": [
      "工具1",
      "工具2"
    ],
    "io_schema": {
      "inputs": [
        {
          "name": "参数名",
          "type": "数据类型",
          "description": "参数描述"
        }
      ],
      "outputs": [
        {
          "name": "输出名",
          "type": "数据类型",
          "description": "输出描述"
        }
      ]
    }
  }

example2 = {
    "workflow_id": "bioinfo_somatic_variant_calling_v1",
    "title": "肿瘤-正常配对样本体细胞变异检测流程",
    "domain_tags": ["生物信息学", "肿瘤基因组学", "变异检测"],
    "description": "基于全外显子组测序数据，识别肿瘤样本特有体细胞突变的标准化分析流程",
    "source_paper_ids": ["ID_12345678", "ID_23456789"],
    "steps": [
      {
        "step_id": 1,
        "logic_description": "对肿瘤和正常样本的原始测序数据进行质量控制，评估数据质量并去除低质量序列和接头污染。",
        "tool_intent": "原始数据质量控制",
        "suggested_tools": ["FastQC", "Trimmomatic", "Fastp"],
        "io_schema": {
          "inputs": [
            {
              "name": "tumor_raw_fastq",
              "type": "FASTQ_FILE",
              "description": "肿瘤样本原始测序数据"
            },
            {
              "name": "normal_raw_fastq",
              "type": "FASTQ_FILE",
              "description": "正常样本原始测序数据"
            }
          ],
          "outputs": [
            {
              "name": "tumor_clean_fastq",
              "type": "FASTQ_FILE",
              "description": "肿瘤样本清洗后测序数据"
            },
            {
              "name": "normal_clean_fastq",
              "type": "FASTQ_FILE",
              "description": "正常样本清洗后测序数据"
            }
          ]
        }
      },
      {
        "step_id": 2,
        "logic_description": "将清洗后的测序数据比对到参考基因组，确定每个序列片段在基因组中的位置。",
        "tool_intent": "序列比对",
        "suggested_tools": ["BWA-MEM", "Bowtie2"],
        "io_schema": {
          "inputs": [
            {
              "name": "tumor_reads",
              "type": "FASTQ_FILE",
              "description": "肿瘤样本清洗后测序数据"
            },
            {
              "name": "normal_reads",
              "type": "FASTQ_FILE",
              "description": "正常样本清洗后测序数据"
            },
            {
              "name": "reference_genome",
              "type": "REFERENCE_GENOME",
              "description": "参考基因组文件"
            }
          ],
          "outputs": [
            {
              "name": "tumor_alignment",
              "type": "BAM_FILE",
              "description": "肿瘤样本比对结果"
            },
            {
              "name": "normal_alignment",
              "type": "BAM_FILE",
              "description": "正常样本比对结果"
            }
          ]
        }
      },
      {
        "step_id": 3,
        "logic_description": "对比对结果进行排序、去重和局部重比对，提高比对质量。",
        "tool_intent": "比对后处理",
        "suggested_tools": ["Samtools", "GATK-MarkDuplicates", "GATK-BQSR"],
        "io_schema": {
          "inputs": [
            {
              "name": "tumor_bam",
              "type": "BAM_FILE",
              "description": "肿瘤样本原始比对结果"
            },
            {
              "name": "normal_bam",
              "type": "BAM_FILE",
              "description": "正常样本原始比对结果"
            }
          ],
          "outputs": [
            {
              "name": "tumor_processed_bam",
              "type": "BAM_FILE",
              "description": "处理后的肿瘤样本比对结果"
            },
            {
              "name": "normal_processed_bam",
              "type": "BAM_FILE",
              "description": "处理后的正常样本比对结果"
            }
          ]
        }
      },
      {
        "step_id": 4,
        "logic_description": "联合分析肿瘤和正常样本的比对结果，识别肿瘤特有的体细胞突变。",
        "tool_intent": "体细胞变异检测",
        "suggested_tools": ["GATK-Mutect2", "Strelka2", "VarScan2"],
        "io_schema": {
          "inputs": [
            {
              "name": "tumor_bam",
              "type": "BAM_FILE",
              "description": "处理后的肿瘤样本比对结果"
            },
            {
              "name": "normal_bam",
              "type": "BAM_FILE",
              "description": "处理后的正常样本比对结果"
            },
            {
              "name": "reference_genome",
              "type": "REFERENCE_GENOME",
              "description": "参考基因组文件"
            },
            {
              "name": "known_variants",
              "type": "VCF_FILE",
              "description": "已知变异数据库"
            }
          ],
          "outputs": [
            {
              "name": "raw_variants",
              "type": "VCF_FILE",
              "description": "原始变异检测结果"
            }
          ]
        }
      },
      {
        "step_id": 5,
        "logic_description": "对检测到的变异进行过滤，去除假阳性结果，并对变异进行功能注释。",
        "tool_intent": "变异过滤与功能注释",
        "suggested_tools": ["GATK-FilterMutectCalls", "SnpEff", "VEP"],
        "io_schema": {
          "inputs": [
            {
              "name": "raw_variants",
              "type": "VCF_FILE",
              "description": "原始变异检测结果"
            },
            {
              "name": "annotation_db",
              "type": "ANNOTATION_DATABASE",
              "description": "基因注释数据库"
            }
          ],
          "outputs": [
            {
              "name": "final_variants",
              "type": "ANNOTATED_VCF",
              "description": "最终注释后的变异结果"
            }
          ]
        }
      },
      {
        "step_id": 6,
        "logic_description": "对最终的变异结果进行统计分析，生成分析报告。",
        "tool_intent": "结果统计与报告生成",
        "suggested_tools": ["R", "Python", "MultiQC"],
        "io_schema": {
          "inputs": [
            {
              "name": "annotated_variants",
              "type": "ANNOTATED_VCF",
              "description": "最终注释后的变异结果"
            }
          ],
          "outputs": [
            {
              "name": "analysis_report",
              "type": "REPORT_PDF",
              "description": "最终分析报告"
            }
          ]
        }
      }
    ]
  }