using UnityEngine;

// Missing class closing brace - intentionally invalid
public class SampleInvalid : MonoBehaviour
{
    private void Update()
    {
        transform.Translate(Vector3.forward * Time.deltaTime)  // missing semicolon
    }
