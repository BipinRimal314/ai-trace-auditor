# PR: docs: Add EU AI Act compliance guide for AutoGen deployers

## Title

docs: Add EU AI Act compliance guide for AutoGen deployers

## Body

AutoGen itself has no EU AI Act obligations (open-source exemption, Article 25(4)). But teams building high-risk applications with AutoGen do, and the August 2, 2026 enforcement deadline is approaching.

This guide helps AutoGen deployers understand which obligations apply to their multi-agent systems under the EU AI Act: scope classification (Annex III), record-keeping (Article 12), transparency (Article 13), value chain accountability (Article 25), and user disclosure (Article 50).

It covers AutoGen-specific implementation details: what to log from agent conversations, how team patterns like `RoundRobinGroupChat` and `SocietyOfMindAgent` map to liability chains, and how to use OpenTelemetry tracing for compliance evidence.

Making compliance accessible for deployers strengthens AutoGen's position as the production-ready multi-agent framework.
