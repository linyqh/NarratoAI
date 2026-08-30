# Streamlit multipage Fusion UI

The project-centered Film Vision Fusion UI will remain inside the existing Streamlit 1.56 application and use dedicated multipage navigation, focused Fusion components, and shared design tokens. This preserves direct access to the local Python media pipeline and durable local task stores while allowing the Project Library, project setup, Fusion Project Workspace, and Task Center to replace the legacy single-page Fusion entry.

We rejected introducing a separate React application and local API layer in this phase because the repository has neither today and that migration would combine a UI remediation with a full application-boundary rewrite. Streamlit implementation must still avoid expanding `webui/components/script_settings.py`: project persistence and policy stay in application services, pages consume stable projections, and custom CSS supplies presentation without becoming the source of workflow state.
